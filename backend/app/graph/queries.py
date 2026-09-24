"""
Travessia do grafo com `$graphLookup` (sem IA, sem `$lookup`).

Por que `$graphLookup` — e por que SEM `$lookup`?
- O modelo é grafo-nativo AUTO-REFERENCIAL: uma coleção única `graph`, cada nó
  com suas arestas de saída embutidas (`arestas: [{to, tipo, props}]`). O
  `$graphLookup` recursa DENTRO dessa coleção (`connectFromField:"arestas.to"` →
  `connectToField:"_id"`), salto a salto.
- A travessia da licença é: licença → (alocação) → projeto → time → centro de
  custo. Os dois últimos saltos (projeto → time → centro) são um caminho de
  profundidade variável na MESMA coleção — o caso canônico do `$graphLookup`
  (`restrictSearchWithMatch` por tipo de NÓ mantém o passeio nos tipos certos).
- Os RÓTULOS saem DIRETO: como cada documento devolvido pelo `$graphLookup` já é
  um nó com seu `label`/`props`, não é preciso NENHUM `$lookup` para hidratar —
  basta filtrar `descendentes` pelo `tipo` do nó desejado e ler `.label`.

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
    """Filtro do find() de licenças na coleção graph (todas, ou 'vence em N dias')."""
    filtro: Dict[str, Any] = {"tipo": "license"}
    if expiring_in_days is not None:
        limite = datetime.utcnow() + timedelta(days=expiring_in_days)
        filtro["props.expires_at"] = {"$lte": limite}
    return filtro


# ---------------------------------------------------------------------------
# Restrição da travessia projeto → time → centro de custo.
# No modelo auto-referencial, restrictSearchWithMatch filtra o NÓ alcançado (por
# `tipo`), não a aresta. Para este grafo é equivalente: cada salto cai num tipo
# de nó distinto, então limitar aos tipos do caminho poda a travessia igual.
_TIPOS_CENTRO = ["project", "team", "cost_center"]


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
    docs = db[C.GRAPH].find(
        _filtro_licencas(expiring_in_days)).sort("props.expires_at", 1)
    return [_licenca_para_api(d) for d in docs]


def consulta_licencas(expiring_in_days: Optional[int] = None) -> str:
    """String mongosh do find() de licenças (o mesmo comando que roda)."""
    return mongosh.formatar_find(
        C.GRAPH, _filtro_licencas(expiring_in_days), {"props.expires_at": 1}
    )


# ---------------------------------------------------------------------------
# Travessia: licença -> (alocação) -> projeto -> time -> centro de custo
# Reaproveitada por "projetos que usam X" e por "impacto se X vencer".
# ---------------------------------------------------------------------------
def _label_por_tipo(tipo_no: str) -> Dict[str, Any]:
    """
    Label do PRIMEIRO nó de um dado `tipo` dentro do array `descendentes` que o
    `$graphLookup` trouxe. Como cada descendente JÁ é um nó completo (com
    `label`), não precisamos de nenhum `$lookup` para resolver o rótulo — só
    filtrar por tipo e ler `.label`.
    """
    return {"$let": {
        "vars": {"n": {"$arrayElemAt": [
            {"$filter": {"input": "$descendentes", "as": "n",
                         "cond": {"$eq": ["$$n.tipo", tipo_no]}}},
            0,
        ]}},
        "in": "$$n.label",
    }}


def _pipeline_travessia(oid: ObjectId) -> List[Dict[str, Any]]:
    """
    Pipeline completo da travessia a partir de uma licença — UM `$graphLookup`,
    ZERO `$lookup`. Fica separado da execução para que o comando exibido em
    "Ver a consulta" seja EXATAMENTE o que roda (inclusive o ObjectId do $match).
    """
    return [
        # Nó de entrada: a licença.
        {"$match": {"_id": oid, "tipo": "license"}},
        # Cada alocação embutida (aresta alocacao license → project) vira 1 linha.
        {"$unwind": "$arestas"},
        {"$match": {"arestas.tipo": E.ALOCACAO}},
        {"$addFields": {
            "project_id": "$arestas.to",
            "quantity": "$arestas.props.quantity",
        }},
        # $graphLookup: a partir do PROJETO, recursa projeto → time → centro
        # DENTRO da própria coleção `graph`. Cada nó devolvido já traz `label`.
        {"$graphLookup": {
            "from": C.GRAPH,
            "startWith": "$project_id",
            "connectFromField": "arestas.to",
            "connectToField": "_id",
            "as": "descendentes",
            "depthField": "nivel",
            "maxDepth": 2,   # projeto(0) → time(1) → centro(2)
            "restrictSearchWithMatch": {"tipo": {"$in": _TIPOS_CENTRO}},
        }},
        # Cada rótulo sai de `descendentes` filtrando pelo tipo do nó (sem $lookup).
        {"$project": {
            "_id": 0,
            "project_id": {"$toString": "$project_id"},
            "project": _label_por_tipo("project"),
            "quantity": "$quantity",
            "team": _label_por_tipo("team"),
            "cost_center": _label_por_tipo("cost_center"),
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
    return list(get_db()[C.GRAPH].aggregate(_pipeline_travessia(oid)))


def consulta_travessia(license_id: str) -> Optional[str]:
    """String mongosh da travessia $graphLookup (o mesmo pipeline que roda)."""
    oid = to_object_id(license_id)
    if oid is None:
        return None
    return mongosh.formatar_aggregate(C.GRAPH, _pipeline_travessia(oid))


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
    lic = db[C.GRAPH].find_one({"_id": oid, "tipo": "license"})
    if lic is None:
        return None

    linhas = projects_using_license(license_id)

    # Servidores dos projetos afetados (relevante p/ VMware, licenciado por host).
    # A aresta servidor → projeto aponta "para cima" (o servidor é a origem), então
    # aqui é uma travessia REVERSA: achamos os nós `server` cuja aresta embutida
    # `servidor_projeto` aponta para um dos projetos afetados.
    projetos_ids = {
        pid for pid in (to_object_id(l["project_id"]) for l in linhas)
        if pid is not None
    }
    servidores = db[C.GRAPH].find(
        {"tipo": "server", "arestas": {"$elemMatch": {
            "tipo": E.SERVIDOR_PROJETO, "to": {"$in": list(projetos_ids)}}}},
        {"label": 1})

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
