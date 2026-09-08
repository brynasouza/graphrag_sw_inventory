"""
Travessia do grafo com `$graphLookup` (sem IA).

Por que `$graphLookup` agora?
- O modelo virou grafo-nativo: `graph_nodes` (entidades) + `graph_edges`
  (relacionamentos homogêneos `{from, to, tipo}`). Numa coleção de arestas
  homogênea, o `$graphLookup` recursa DE VERDADE: parte de um nó e segue
  `to → from` salto a salto, sem precisar de um `$lookup` por etapa.
- A travessia da licença é: licença → (alocação) → projeto → time → centro de
  custo. Os dois últimos saltos (projeto → time → centro) são um caminho de
  profundidade variável na MESMA coleção de arestas — o caso natural do
  `$graphLookup` (`restrictSearchWithMatch` mantém o passeio nos tipos certos).
- Os RÓTULOS dos nós alcançados vêm de um ÚNICO `$lookup` em `graph_nodes` (o
  `$graphLookup` traz as arestas do caminho; para exibir "Datacenter
  Virtualização" em vez do ObjectId, resolvemos os nós). Um só `$lookup` com
  `$in` traz projeto + time + centro de uma vez. Isso é padrão até nos próprios
  exemplos de grafo do MongoDB — o destaque "$graphLookup" fica no passeio
  multi-salto.

Cada função devolve dados já prontos para virar JSON (ObjectId -> str).
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from bson import ObjectId
from bson.errors import InvalidId

from app.core.db import get_db
from app.graph import mongosh
from app.models.schemas import Collections as C
from app.models.schemas import EdgeTypes as E


def to_object_id(value: str) -> Optional[ObjectId]:
    """Converte texto em ObjectId; devolve None se o formato for inválido."""
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


# ---------------------------------------------------------------------------
# Listagem de licenças (nós tipo "license")
# ---------------------------------------------------------------------------
def _filtro_licencas(expiring_in_days: Optional[int] = None) -> Dict[str, Any]:
    """Filtro do find() de licenças em graph_nodes (todas, ou 'vence em N dias')."""
    filtro: Dict[str, Any] = {"tipo": "license"}
    if expiring_in_days is not None:
        limite = datetime.utcnow() + timedelta(days=expiring_in_days)
        filtro["props.expires_at"] = {"$lte": limite}
    return filtro


def _licenca_para_api(node: Dict[str, Any]) -> Dict[str, Any]:
    """Achata um nó de licença na forma que a API/o frontend esperam."""
    props = node.get("props", {})
    expira = props.get("expires_at")
    return {
        "_id": str(node["_id"]),
        "name": node.get("label", ""),
        "expires_at": expira.isoformat() if isinstance(expira, datetime) else expira,
        "unit_cost": props.get("unit_cost"),
        "currency": props.get("currency"),
        "metric": props.get("metric"),
    }


def list_licenses(expiring_in_days: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Lista licenças. Se expiring_in_days for informado, filtra as que
    vencem nesse número de dias a partir de agora.
    """
    db = get_db()
    docs = db[C.GRAPH_NODES].find(
        _filtro_licencas(expiring_in_days)).sort("props.expires_at", 1)
    return [_licenca_para_api(d) for d in docs]


def consulta_licencas(expiring_in_days: Optional[int] = None) -> str:
    """String mongosh do find() de licenças (o mesmo comando que roda)."""
    return mongosh.formatar_find(
        C.GRAPH_NODES, _filtro_licencas(expiring_in_days), {"props.expires_at": 1}
    )


# ---------------------------------------------------------------------------
# Travessia: licença -> (alocação) -> projeto -> time -> centro de custo
# Reaproveitada por "projetos que usam X" e por "impacto se X vencer".
# ---------------------------------------------------------------------------
def _extrair_destino(caminho_field: str, tipo_aresta: str) -> Dict[str, Any]:
    """
    Expressão que pega o `to` da PRIMEIRA aresta de um dado tipo dentro do
    array de caminho trazido pelo $graphLookup. É como "andamos" do array de
    arestas recursivas até o nó específico (time, centro de custo…).
    """
    return {"$arrayElemAt": [
        {"$map": {
            "input": {"$filter": {
                "input": f"${caminho_field}", "as": "e",
                "cond": {"$eq": ["$$e.tipo", tipo_aresta]},
            }},
            "as": "e", "in": "$$e.to",
        }},
        0,
    ]}


def _label_de(campo_id: str) -> Dict[str, Any]:
    """
    Label do nó cujo `_id == campo_id`, buscado dentro do array `nos` que um
    ÚNICO `$lookup` já carregou (projeto + time + centro de uma vez). Assim não
    precisamos de um `$lookup` separado por rótulo. `campo_id` é a referência ao
    campo (ex.: "$alloc.to", "$team_id").
    """
    return {"$let": {
        "vars": {"n": {"$arrayElemAt": [
            {"$filter": {"input": "$nos", "as": "n",
                         "cond": {"$eq": ["$$n._id", campo_id]}}},
            0,
        ]}},
        "in": "$$n.label",
    }}


def _pipeline_travessia(oid: ObjectId) -> List[Dict[str, Any]]:
    """
    Pipeline completo da travessia a partir de uma licença.
    Fica separado da execução para que o comando exibido em "Ver a consulta"
    seja EXATAMENTE o que roda no banco (inclusive o ObjectId real do $match).
    """
    return [
        # Nó de entrada: a licença.
        {"$match": {"_id": oid, "tipo": "license"}},
        # Alocações desta licença (arestas alocacao license → project).
        {"$lookup": {
            "from": C.GRAPH_EDGES,
            "localField": "_id",
            "foreignField": "from",
            "pipeline": [
                {"$match": {"tipo": E.ALOCACAO}},
                {"$project": {"to": 1, "quantity": "$props.quantity", "_id": 0}},
            ],
            "as": "alloc",
        }},
        {"$unwind": "$alloc"},
        # $graphLookup: a partir do PROJETO, recursa projeto → time → centro.
        {"$graphLookup": {
            "from": C.GRAPH_EDGES,
            "startWith": "$alloc.to",
            "connectFromField": "to",
            "connectToField": "from",
            "as": "caminho",
            "depthField": "nivel",
            "restrictSearchWithMatch": {
                "tipo": {"$in": [E.PROJETO_TIME, E.TIME_CENTRO]}
            },
        }},
        # Extrai os nós de time e centro de custo de dentro do caminho recursivo.
        {"$addFields": {
            "team_id": _extrair_destino("caminho", E.PROJETO_TIME),
            "cost_center_id": _extrair_destino("caminho", E.TIME_CENTRO),
        }},
        # UM único $lookup traz os rótulos de projeto + time + centro de uma vez
        # (os três _id de interesse num $in), em vez de um $lookup por rótulo.
        {"$lookup": {
            "from": C.GRAPH_NODES,
            "let": {"ids": ["$alloc.to", "$team_id", "$cost_center_id"]},
            "pipeline": [
                {"$match": {"$expr": {"$in": ["$_id", "$$ids"]}}},
                {"$project": {"_id": 1, "label": 1}},
            ],
            "as": "nos",
        }},
        # Cada rótulo sai do array `nos` casando pelo _id (helper _label_de).
        {"$project": {
            "_id": 0,
            "project_id": {"$toString": "$alloc.to"},
            "project": _label_de("$alloc.to"),
            "quantity": "$alloc.quantity",
            "team": _label_de("$team_id"),
            "cost_center": _label_de("$cost_center_id"),
        }},
        {"$sort": {"project": 1}},
    ]


def projects_using_license(license_id: str) -> List[Dict[str, Any]]:
    """
    "Quais projetos usam a licença X?"
    Devolve cada projeto com quantidade alocada, time e centro de custo.
    """
    oid = to_object_id(license_id)
    if oid is None:
        return []
    return list(get_db()[C.GRAPH_NODES].aggregate(_pipeline_travessia(oid)))


def consulta_travessia(license_id: str) -> Optional[str]:
    """String mongosh da travessia $graphLookup (o mesmo pipeline que roda)."""
    oid = to_object_id(license_id)
    if oid is None:
        return None
    return mongosh.formatar_aggregate(C.GRAPH_NODES, _pipeline_travessia(oid))


def license_impact(license_id: str) -> Optional[Dict[str, Any]]:
    """
    "Se a licença X expirar, quais times/projetos/centros são impactados?"
    Consolida o alcance da licença: projetos, times, centros de custo e
    servidores afetados, além da data de expiração.
    """
    oid = to_object_id(license_id)
    if oid is None:
        return None

    db = get_db()
    lic = db[C.GRAPH_NODES].find_one({"_id": oid, "tipo": "license"})
    if lic is None:
        return None

    linhas = projects_using_license(license_id)

    # Servidores dos projetos afetados (relevante p/ VMware, licenciado por host).
    # A travessia já trouxe o project_id de cada alocação; a partir dele achamos
    # as arestas servidor → projeto e, delas, os nós de servidor.
    projetos_ids = {
        pid for pid in (to_object_id(l["project_id"]) for l in linhas)
        if pid is not None
    }
    arestas_srv = db[C.GRAPH_EDGES].find(
        {"tipo": E.SERVIDOR_PROJETO, "to": {"$in": list(projetos_ids)}}, {"from": 1})
    server_ids = [e["from"] for e in arestas_srv]
    servidores = db[C.GRAPH_NODES].find(
        {"_id": {"$in": server_ids}, "tipo": "server"}, {"label": 1})

    props = lic.get("props", {})
    expira = props.get("expires_at")
    return {
        "license": lic.get("label", ""),
        "expires_at": expira.isoformat() if isinstance(expira, datetime) else expira,
        "metric": props.get("metric"),
        "impacted_projects": sorted({l["project"] for l in linhas}),
        "impacted_teams": sorted({l["team"] for l in linhas}),
        "impacted_cost_centers": sorted({l["cost_center"] for l in linhas}),
        "impacted_servers": [s["label"] for s in servidores],
        "detail": linhas,
    }
