"""
Travessia do grafo com $lookup encadeado (sem IA).

Por que $lookup encadeado e não $graphLookup?
- $graphLookup serve para percorrer uma coleção que aponta para ela
  mesma (hierarquia de profundidade variável, ex.: chefe -> chefe -> ...).
- Nosso caminho atravessa COLEÇÕES DIFERENTES com profundidade fixa e
  conhecida: licença -> allocations -> projeto -> time -> centro de custo.
  Para isso, o certo é um $lookup por salto (um "join" por etapa).

Cada função devolve dados já prontos para virar JSON (ObjectId -> str).
"""
from typing import Any, Dict, List, Optional

from bson import ObjectId
from bson.errors import InvalidId

from app.core.db import get_db
from app.graph import mongosh
from app.models.schemas import Collections as C


def to_object_id(value: str) -> Optional[ObjectId]:
    """Converte texto em ObjectId; devolve None se o formato for inválido."""
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


def _clean(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Transforma ObjectId em str para o documento virar JSON sem erro."""
    out = {}
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            out[k] = str(v)
        elif isinstance(v, list):
            out[k] = [_clean(i) if isinstance(i, dict) else str(i)
                      if isinstance(i, ObjectId) else i for i in v]
        elif isinstance(v, dict):
            out[k] = _clean(v)
        else:
            out[k] = v
    return out


def _filtro_licencas(expiring_in_days: Optional[int] = None) -> Dict[str, Any]:
    """Filtro do find() de licenças (vazio, ou 'vence em N dias')."""
    from datetime import datetime, timedelta

    if expiring_in_days is None:
        return {}
    limite = datetime.utcnow() + timedelta(days=expiring_in_days)
    return {"expires_at": {"$lte": limite}}


def list_licenses(expiring_in_days: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Lista licenças. Se expiring_in_days for informado, filtra as que
    vencem nesse número de dias a partir de agora.
    """
    db = get_db()
    docs = db[C.LICENSES].find(_filtro_licencas(expiring_in_days)).sort("expires_at", 1)
    return [_clean(d) for d in docs]


def consulta_licencas(expiring_in_days: Optional[int] = None) -> str:
    """String mongosh do find() de licenças (o mesmo comando que roda)."""
    return mongosh.formatar_find(
        C.LICENSES, _filtro_licencas(expiring_in_days), {"expires_at": 1}
    )


# ---------------------------------------------------------------------------
# Pipeline de travessia: licença -> allocations -> projeto -> time -> centro
# Reaproveitado pelas consultas de "projetos que usam X" e "impacto se X vencer"
# ---------------------------------------------------------------------------
def _traversal_stages() -> List[Dict[str, Any]]:
    # Cada $lookup mantém localField/foreignField (join indexado — IXSCAN) e traz
    # só os campos usados a jusante via sub-pipeline $project, em vez do documento
    # inteiro. Forma combinada do MongoDB 5.0+ (igualdade indexada + projeção).
    return [
        # Salto 1: licença -> alocações desta licença
        {"$lookup": {
            "from": C.ALLOCATIONS,
            "localField": "_id",
            "foreignField": "license_id",
            "pipeline": [{"$project": {"project_id": 1, "quantity": 1, "_id": 0}}],
            "as": "alloc",
        }},
        {"$unwind": "$alloc"},
        # Salto 2: alocação -> projeto
        {"$lookup": {
            "from": C.PROJECTS,
            "localField": "alloc.project_id",
            "foreignField": "_id",
            "pipeline": [{"$project": {"name": 1, "team_id": 1, "_id": 0}}],
            "as": "project",
        }},
        {"$unwind": "$project"},
        # Salto 3: projeto -> time
        {"$lookup": {
            "from": C.TEAMS,
            "localField": "project.team_id",
            "foreignField": "_id",
            "pipeline": [{"$project": {"name": 1, "cost_center_id": 1, "_id": 0}}],
            "as": "team",
        }},
        {"$unwind": "$team"},
        # Salto 4: time -> centro de custo
        {"$lookup": {
            "from": C.COST_CENTERS,
            "localField": "team.cost_center_id",
            "foreignField": "_id",
            "pipeline": [{"$project": {"code": 1, "_id": 0}}],
            "as": "cost_center",
        }},
        {"$unwind": "$cost_center"},
    ]


def _pipeline_travessia(oid: ObjectId) -> List[Dict[str, Any]]:
    """
    Pipeline completo da travessia a partir de uma licença.
    Fica separado da execução para que o comando exibido em "Ver a consulta"
    seja EXATAMENTE o que roda no banco (inclusive o ObjectId real do $match).
    """
    return [{"$match": {"_id": oid}}] + _traversal_stages() + [
        {"$project": {
            "_id": 0,
            "project_id": {"$toString": "$alloc.project_id"},
            "project": "$project.name",
            "quantity": "$alloc.quantity",
            "team": "$team.name",
            "cost_center": "$cost_center.code",
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

    return list(get_db()[C.LICENSES].aggregate(_pipeline_travessia(oid)))


def consulta_travessia(license_id: str) -> Optional[str]:
    """String mongosh da travessia $lookup encadeada (o mesmo pipeline que roda)."""
    oid = to_object_id(license_id)
    if oid is None:
        return None
    return mongosh.formatar_aggregate(C.LICENSES, _pipeline_travessia(oid))


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
    lic = db[C.LICENSES].find_one({"_id": oid})
    if lic is None:
        return None

    linhas = projects_using_license(license_id)

    # Servidores dos projetos afetados (relevante p/ VMware, licenciado por host).
    # A travessia já trouxe o project_id de cada alocação — usamos ele direto
    # (join por _id), sem uma consulta extra buscando os projetos pelo nome.
    nomes_projetos = {l["project"] for l in linhas}
    projetos_ids = {
        pid for pid in (to_object_id(l["project_id"]) for l in linhas)
        if pid is not None
    }
    servidores = [_clean(s) for s in db[C.SERVERS].find(
        {"project_id": {"$in": list(projetos_ids)}})]

    return {
        "license": lic["name"],
        "expires_at": lic["expires_at"].isoformat(),
        "metric": lic.get("metric"),
        "impacted_projects": sorted(nomes_projetos),
        "impacted_teams": sorted({l["team"] for l in linhas}),
        "impacted_cost_centers": sorted({l["cost_center"] for l in linhas}),
        "impacted_servers": [s["hostname"] for s in servidores],
        "detail": linhas,
    }
