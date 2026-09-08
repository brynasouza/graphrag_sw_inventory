"""
Agregações de custo (Etapa 4) — sobre o grafo (`graph_edges` + `graph_nodes`).

O gasto real de cada alocação é: unit_cost (do NÓ licença) x quantity (da ARESTA
de alocação). Somamos isso agrupando por centro de custo ou por fornecedor.

Começamos SEMPRE pelas ARESTAS de alocação (`tipo:"alocacao"`), porque é nelas
que mora a quantidade — sem quantidade não há gasto para somar. Do centro de
custo e do fornecedor chegamos com `$graphLookup`, recursando pela coleção de
arestas homogênea (projeto → time → centro; licença → produto → fornecedor).

Nota honesta de tradeoff: custo é AGREGAÇÃO PONDERADA POR CAMINHO (quantity x
unit_cost, somado por centro/moeda). O `$graphLookup` coleta ALCANÇABILIDADE,
não soma pesos por aresta — então precisamos extrair o nó final do caminho e
agrupar depois. Fica mais verboso (e o `explain()` não mostra o IXSCAN 1:1
limpo de um `$lookup` por salto), mas roda sobre o mesmo grafo que a demo exibe.
"""
from typing import Any, Dict, List, Optional

from app.core.db import get_db
from app.graph import mongosh
from app.models.schemas import Collections as C
from app.models.schemas import EdgeTypes as E

# Estágios comuns: aresta de alocação -> NÓ licença (traz unit_cost/moeda) e o
# "gasto" de cada linha (quantidade da aresta x custo unitário da licença).
_LICENSE_JOIN = [
    {"$lookup": {
        "from": C.GRAPH_NODES,
        "localField": "from",          # a alocação sai da licença
        "foreignField": "_id",
        "pipeline": [{"$project": {
            "unit_cost": "$props.unit_cost", "currency": "$props.currency", "_id": 0}}],
        "as": "lic",
    }},
    {"$unwind": "$lic"},
    # gasto da alocação = quantidade (aresta) x custo unitário (licença)
    {"$addFields": {
        "spend": {"$multiply": ["$props.quantity", "$lic.unit_cost"]},
    }},
]


def _cadeia_fornecedor() -> List[Dict[str, Any]]:
    """$graphLookup licença → produto → fornecedor; expõe o NÓ `vendor`."""
    return [
        {"$graphLookup": {
            "from": C.GRAPH_EDGES,
            "startWith": "$from",             # a licença
            "connectFromField": "to",
            "connectToField": "from",
            "as": "cadeia_fornecedor",
            "restrictSearchWithMatch": {
                "tipo": {"$in": [E.LICENCA_PRODUTO, E.PRODUTO_FORNECEDOR]}
            },
        }},
        {"$addFields": {"vendor_id": {"$arrayElemAt": [
            {"$map": {
                "input": {"$filter": {
                    "input": "$cadeia_fornecedor", "as": "e",
                    "cond": {"$eq": ["$$e.tipo", E.PRODUTO_FORNECEDOR]}}},
                "as": "e", "in": "$$e.to"}},
            0]}}},
        {"$lookup": {
            "from": C.GRAPH_NODES, "localField": "vendor_id", "foreignField": "_id",
            "pipeline": [{"$project": {"name": "$label", "_id": 0}}], "as": "vendor"}},
        {"$unwind": "$vendor"},
    ]


def _cadeia_centro() -> List[Dict[str, Any]]:
    """$graphLookup projeto → time → centro; expõe o NÓ `cc` (code + name)."""
    return [
        {"$graphLookup": {
            "from": C.GRAPH_EDGES,
            "startWith": "$to",               # o projeto da alocação
            "connectFromField": "to",
            "connectToField": "from",
            "as": "cadeia_centro",
            "restrictSearchWithMatch": {
                "tipo": {"$in": [E.PROJETO_TIME, E.TIME_CENTRO]}
            },
        }},
        {"$addFields": {"cost_center_id": {"$arrayElemAt": [
            {"$map": {
                "input": {"$filter": {
                    "input": "$cadeia_centro", "as": "e",
                    "cond": {"$eq": ["$$e.tipo", E.TIME_CENTRO]}}},
                "as": "e", "in": "$$e.to"}},
            0]}}},
        {"$lookup": {
            "from": C.GRAPH_NODES, "localField": "cost_center_id", "foreignField": "_id",
            "pipeline": [{"$project": {"code": "$label", "name": "$props.name", "_id": 0}}],
            "as": "cc"}},
        {"$unwind": "$cc"},
    ]


# ---------------------------------------------------------------------------
# Montagem dos pipelines (separada da execução)
# Manter a construção do pipeline numa função só garante que o comando exibido
# na tela ("Ver a consulta") é EXATAMENTE o que roda no banco.
# ---------------------------------------------------------------------------
def _pipeline_por_centro(vendor: Optional[str] = None) -> List[Dict[str, Any]]:
    """Pipeline do gasto por centro de custo (opcionalmente filtrado por fornecedor)."""
    pipeline: List[Dict[str, Any]] = [{"$match": {"tipo": E.ALOCACAO}}]
    pipeline += _LICENSE_JOIN

    # Se filtrar por fornecedor, sobe licença → produto → fornecedor e casa o nome.
    if vendor:
        pipeline += _cadeia_fornecedor()
        pipeline += [{"$match": {"vendor.name": vendor}}]

    # projeto → time → centro de custo, então agrupa.
    pipeline += _cadeia_centro()
    pipeline += [
        # A MOEDA entra na CHAVE do grupo, não num $first. Assim, gastos em
        # moedas diferentes NUNCA são somados sob o mesmo total: cada
        # (centro de custo, moeda) vira uma linha separada. Somar BRL+USD sem
        # conversão e rotular com uma moeda só seria silenciosamente errado.
        {"$group": {
            "_id": {"code": "$cc.code", "name": "$cc.name", "currency": "$lic.currency"},
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
    """Pipeline do gasto por fornecedor (alocação → licença → produto → fornecedor)."""
    pipeline: List[Dict[str, Any]] = [{"$match": {"tipo": E.ALOCACAO}}]
    pipeline += _LICENSE_JOIN
    pipeline += _cadeia_fornecedor()
    pipeline += [
        # Moeda na CHAVE do grupo (ver justificativa em _pipeline_por_centro):
        # gastos em moedas diferentes nunca colapsam num único total.
        {"$group": {
            "_id": {"vendor": "$vendor.name", "currency": "$lic.currency"},
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
    return list(get_db()[C.GRAPH_EDGES].aggregate(_pipeline_por_centro(vendor)))


def cost_by_vendor() -> List[Dict[str, Any]]:
    """Gasto total por fornecedor (alocação → licença → produto → fornecedor)."""
    return list(get_db()[C.GRAPH_EDGES].aggregate(_pipeline_por_fornecedor()))


# ---------------------------------------------------------------------------
# Versões "só o comando" (para o painel "Ver a consulta")
# ---------------------------------------------------------------------------
def consulta_por_centro(vendor: Optional[str] = None) -> str:
    """String mongosh do gasto por centro de custo (o mesmo pipeline que roda)."""
    return mongosh.formatar_aggregate(C.GRAPH_EDGES, _pipeline_por_centro(vendor))


def consulta_por_fornecedor() -> str:
    """String mongosh do gasto por fornecedor (o mesmo pipeline que roda)."""
    return mongosh.formatar_aggregate(C.GRAPH_EDGES, _pipeline_por_fornecedor())
