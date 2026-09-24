"""
Agregações de custo (Etapa 4) — sobre a coleção auto-referencial `graph`.

O gasto real de cada alocação é: unit_cost (do NÓ licença) x quantity (da ARESTA
de alocação, embutida na própria licença). Como os dois moram no MESMO documento
(a licença), o gasto de cada linha é calculado LOCALMENTE, sem nenhum `$lookup`:
partimos das licenças (`tipo:"license"`), desdobramos suas arestas `alocacao`
(`$unwind`) e multiplicamos `arestas.props.quantity` por `props.unit_cost`.

O nó final (fornecedor ou centro de custo) vem por `$graphLookup` recursando
DENTRO de `graph` — e como cada documento devolvido já é um nó com `label`/`props`,
extraímos o nó desejado do resultado por `tipo`, sem `$lookup` para hidratar.

Nota honesta de tradeoff: custo é AGREGAÇÃO PONDERADA POR CAMINHO (quantity x
unit_cost, somado por centro/moeda). O `$graphLookup` coleta ALCANÇABILIDADE,
não soma pesos por aresta — então extraímos o nó final e agrupamos depois. E como
o modelo é auto-referencial, `restrictSearchWithMatch` filtra o NÓ alcançado (por
`tipo`), não a aresta; para este grafo é equivalente (cada salto cai num tipo
distinto).
"""
from typing import Any, Dict, List, Optional

from app.core.db import get_db
from app.graph import mongosh
from app.models.schemas import Collections as C
from app.models.schemas import EdgeTypes as E


def _extrai_no(campo_array: str, tipo_no: str) -> Dict[str, Any]:
    """
    Extrai o PRIMEIRO nó de um dado `tipo` de dentro do array que o
    `$graphLookup` trouxe. Cada elemento já é um nó completo (com `label`/`props`),
    então não é preciso `$lookup` para saber quem ele é.
    """
    return {"$arrayElemAt": [
        {"$filter": {"input": f"${campo_array}", "as": "n",
                     "cond": {"$eq": ["$$n.tipo", tipo_no]}}},
        0,
    ]}


# Gasto de cada alocação = quantidade (aresta embutida) x custo unitário (nó
# licença). Ambos vivem no MESMO documento -> multiplicação LOCAL, sem join.
_SPEND_LOCAL = {"$multiply": ["$arestas.props.quantity", "$props.unit_cost"]}


def _cadeia_fornecedor() -> List[Dict[str, Any]]:
    """$graphLookup licença → produto → fornecedor; expõe o NÓ `vendor`.

    Roda ANTES do `$unwind` das alocações, enquanto o array `arestas` completo
    da licença ainda tem as arestas `licenca_produto`.
    """
    return [
        {"$graphLookup": {
            "from": C.GRAPH,
            "startWith": "$arestas.to",       # todos os destinos de saída da licença
            "connectFromField": "arestas.to",
            "connectToField": "_id",
            "as": "cadeia_fornecedor",
            "maxDepth": 1,                    # produto(0) → fornecedor(1)
            "restrictSearchWithMatch": {"tipo": {"$in": ["product", "vendor"]}},
        }},
        {"$addFields": {"vendor": _extrai_no("cadeia_fornecedor", "vendor")}},
    ]


def _cadeia_centro() -> List[Dict[str, Any]]:
    """$graphLookup projeto → time → centro; expõe o NÓ `cc` (label + props.name).

    Roda DEPOIS do `$unwind`, a partir do `project_id` de cada alocação.
    """
    return [
        {"$graphLookup": {
            "from": C.GRAPH,
            "startWith": "$project_id",       # o projeto da alocação
            "connectFromField": "arestas.to",
            "connectToField": "_id",
            "as": "cadeia_centro",
            "maxDepth": 2,                    # projeto(0) → time(1) → centro(2)
            "restrictSearchWithMatch": {
                "tipo": {"$in": ["project", "team", "cost_center"]}},
        }},
        {"$addFields": {"cc": _extrai_no("cadeia_centro", "cost_center")}},
    ]


# ---------------------------------------------------------------------------
# Montagem dos pipelines (separada da execução)
# Manter a construção do pipeline numa função só garante que o comando exibido
# na tela ("Ver a consulta") é EXATAMENTE o que roda no banco.
# ---------------------------------------------------------------------------
def _pipeline_por_centro(vendor: Optional[str] = None) -> List[Dict[str, Any]]:
    """Pipeline do gasto por centro de custo (opcionalmente filtrado por fornecedor)."""
    # Partimos das LICENÇAS: nelas moram unit_cost/moeda e as arestas de alocação.
    pipeline: List[Dict[str, Any]] = [{"$match": {"tipo": "license"}}]

    # Se filtrar por fornecedor, sobe licença → produto → fornecedor ANTES de
    # desdobrar as alocações (enquanto o array `arestas` completo ainda existe).
    if vendor:
        pipeline += _cadeia_fornecedor()
        pipeline += [{"$match": {"vendor.label": vendor}}]

    # Uma linha por alocação, com o gasto calculado LOCALMENTE (sem join).
    pipeline += [
        {"$unwind": "$arestas"},
        {"$match": {"arestas.tipo": E.ALOCACAO}},
        {"$addFields": {"project_id": "$arestas.to", "spend": _SPEND_LOCAL}},
    ]

    # projeto → time → centro de custo, então agrupa.
    pipeline += _cadeia_centro()
    pipeline += [
        # A MOEDA entra na CHAVE do grupo, não num $first. Assim, gastos em
        # moedas diferentes NUNCA são somados sob o mesmo total: cada
        # (centro de custo, moeda) vira uma linha separada. Somar BRL+USD sem
        # conversão e rotular com uma moeda só seria silenciosamente errado.
        {"$group": {
            "_id": {"code": "$cc.label", "name": "$cc.props.name",
                    "currency": "$props.currency"},
            "total": {"$sum": "$spend"},
        }},
        {"$project": {
            "_id": 0,
            "cost_center": "$_id.code",
            "cost_center_name": "$_id.name",
            "currency": "$_id.currency",
            "total": 1,
        }},
        {"$sort": {"total": -1}},
    ]
    return pipeline


def _pipeline_por_fornecedor() -> List[Dict[str, Any]]:
    """Pipeline do gasto por fornecedor (licença → produto → fornecedor + alocações)."""
    pipeline: List[Dict[str, Any]] = [{"$match": {"tipo": "license"}}]
    # Fornecedor da licença ANTES do $unwind (precisa das arestas licenca_produto).
    pipeline += _cadeia_fornecedor()
    pipeline += [
        {"$unwind": "$arestas"},
        {"$match": {"arestas.tipo": E.ALOCACAO}},
        {"$addFields": {"spend": _SPEND_LOCAL}},
        # Moeda na CHAVE do grupo (ver justificativa em _pipeline_por_centro):
        # gastos em moedas diferentes nunca colapsam num único total.
        {"$group": {
            "_id": {"vendor": "$vendor.label", "currency": "$props.currency"},
            "total": {"$sum": "$spend"},
        }},
        {"$project": {"_id": 0, "vendor": "$_id.vendor", "currency": "$_id.currency", "total": 1}},
        {"$sort": {"total": -1}},
    ]
    return pipeline


def cost_by_cost_center(vendor: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Gasto total por centro de custo.
    Se `vendor` for informado, considera só as licenças daquele fornecedor
    (responde: 'quanto gastamos com o fornecedor Y por centro de custo?').
    """
    return list(get_db()[C.GRAPH].aggregate(_pipeline_por_centro(vendor)))


def cost_by_vendor() -> List[Dict[str, Any]]:
    """Gasto total por fornecedor (licença → produto → fornecedor)."""
    return list(get_db()[C.GRAPH].aggregate(_pipeline_por_fornecedor()))


# ---------------------------------------------------------------------------
# Versões "só o comando" (para o painel "Ver a consulta")
# ---------------------------------------------------------------------------
def consulta_por_centro(vendor: Optional[str] = None) -> str:
    """String mongosh do gasto por centro de custo (o mesmo pipeline que roda)."""
    return mongosh.formatar_aggregate(C.GRAPH, _pipeline_por_centro(vendor))


def consulta_por_fornecedor() -> str:
    """String mongosh do gasto por fornecedor (o mesmo pipeline que roda)."""
    return mongosh.formatar_aggregate(C.GRAPH, _pipeline_por_fornecedor())
