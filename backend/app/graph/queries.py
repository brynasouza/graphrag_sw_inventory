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


def list_licenses(expiring_in_days: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Lista licenças. Se expiring_in_days for informado, filtra as que
    vencem nesse número de dias a partir de agora.
    """
    from datetime import datetime, timedelta

    db = get_db()
    filtro: Dict[str, Any] = {}
    if expiring_in_days is not None:
        limite = datetime.utcnow() + timedelta(days=expiring_in_days)
        filtro = {"expires_at": {"$lte": limite}}

    docs = db[C.LICENSES].find(filtro).sort("expires_at", 1)
    return [_clean(d) for d in docs]


# ---------------------------------------------------------------------------
# Pipeline de travessia: licença -> allocations -> projeto -> time -> centro
# Reaproveitado pelas consultas de "projetos que usam X" e "impacto se X vencer"
# ---------------------------------------------------------------------------
def _traversal_stages() -> List[Dict[str, Any]]:
    return [
        # Salto 1: licença -> alocações desta licença
        {"$lookup": {
            "from": C.ALLOCATIONS,
            "localField": "_id",
            "foreignField": "license_id",
            "as": "alloc",
        }},
        {"$unwind": "$alloc"},
        # Salto 2: alocação -> projeto
        {"$lookup": {
            "from": C.PROJECTS,
            "localField": "alloc.project_id",
            "foreignField": "_id",
            "as": "project",
        }},
        {"$unwind": "$project"},
        # Salto 3: projeto -> time
        {"$lookup": {
            "from": C.TEAMS,
            "localField": "project.team_id",
            "foreignField": "_id",
            "as": "team",
        }},
        {"$unwind": "$team"},
        # Salto 4: time -> centro de custo
        {"$lookup": {
            "from": C.COST_CENTERS,
            "localField": "team.cost_center_id",
            "foreignField": "_id",
            "as": "cost_center",
        }},
        {"$unwind": "$cost_center"},
    ]


def projects_using_license(license_id: str) -> List[Dict[str, Any]]:
    """
    "Quais projetos usam a licença X?"
    Devolve cada projeto com quantidade alocada, time e centro de custo.
    """
    oid = to_object_id(license_id)
    if oid is None:
        return []

    db = get_db()
    pipeline = [{"$match": {"_id": oid}}] + _traversal_stages() + [
        {"$project": {
            "_id": 0,
            "project": "$project.name",
            "quantity": "$alloc.quantity",
            "team": "$team.name",
            "cost_center": "$cost_center.code",
        }},
        {"$sort": {"project": 1}},
    ]
    return list(db[C.LICENSES].aggregate(pipeline))


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

    # Servidores dos projetos afetados (relevante p/ VMware, licenciado por host)
    nomes_projetos = {l["project"] for l in linhas}
    projetos_ids = [p["_id"] for p in db[C.PROJECTS].find(
        {"name": {"$in": list(nomes_projetos)}}, {"_id": 1})]
    servidores = [_clean(s) for s in db[C.SERVERS].find(
        {"project_id": {"$in": projetos_ids}})]

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
