"""
Agregações de custo (Etapa 4).

O gasto real de cada alocação é: unit_cost (da licença) x quantity (da
alocação). Somamos isso agrupando por centro de custo ou por fornecedor.

Começamos SEMPRE pela coleção `allocations`, porque é ela que guarda a
quantidade — sem quantidade não há gasto para somar.
"""
from typing import Any, Dict, List, Optional

from app.core.db import get_db
from app.graph import mongosh
from app.models.schemas import Collections as C

# Estágios comuns: allocations -> licença (traz unit_cost) e o "gasto" de cada linha
_LICENSE_JOIN = [
    {"$lookup": {
        "from": C.LICENSES,
        "localField": "license_id",
        "foreignField": "_id",
        "as": "lic",
    }},
    {"$unwind": "$lic"},
    # gasto da alocação = quantidade x custo unitário
    {"$addFields": {
        "spend": {"$multiply": ["$quantity", "$lic.unit_cost"]},
    }},
]


# ---------------------------------------------------------------------------
# Montagem dos pipelines (separada da execução)
# Manter a construção do pipeline numa função só garante que o comando exibido
# na tela ("Ver a consulta") é EXATAMENTE o que roda no banco.
# ---------------------------------------------------------------------------
def _pipeline_por_centro(vendor: Optional[str] = None) -> List[Dict[str, Any]]:
    """Pipeline do gasto por centro de custo (opcionalmente filtrado por fornecedor)."""
    pipeline: List[Dict[str, Any]] = list(_LICENSE_JOIN)

    # Se filtrar por fornecedor, precisamos subir licença -> produto -> fornecedor
    if vendor:
        pipeline += [
            {"$lookup": {"from": C.PRODUCTS, "localField": "lic.product_id",
                         "foreignField": "_id", "as": "product"}},
            {"$unwind": "$product"},
            {"$lookup": {"from": C.VENDORS, "localField": "product.vendor_id",
                         "foreignField": "_id", "as": "vendor"}},
            {"$unwind": "$vendor"},
            {"$match": {"vendor.name": vendor}},
        ]

    # allocation -> projeto -> time -> centro de custo
    pipeline += [
        {"$lookup": {"from": C.PROJECTS, "localField": "project_id",
                     "foreignField": "_id", "as": "project"}},
        {"$unwind": "$project"},
        {"$lookup": {"from": C.TEAMS, "localField": "project.team_id",
                     "foreignField": "_id", "as": "team"}},
        {"$unwind": "$team"},
        {"$lookup": {"from": C.COST_CENTERS, "localField": "team.cost_center_id",
                     "foreignField": "_id", "as": "cc"}},
        {"$unwind": "$cc"},
        {"$group": {
            "_id": {"code": "$cc.code", "name": "$cc.name"},
            "total": {"$sum": "$spend"},
            "currency": {"$first": "$lic.currency"},
        }},
        {"$project": {
            "_id": 0,
            "cost_center": "$_id.code",
            "cost_center_name": "$_id.name",
            "total": 1,
            "currency": 1,
        }},
        {"$sort": {"total": -1}},
    ]
    return pipeline


def _pipeline_por_fornecedor() -> List[Dict[str, Any]]:
    """Pipeline do gasto por fornecedor (allocations -> licença -> produto -> fornecedor)."""
    return list(_LICENSE_JOIN) + [
        {"$lookup": {"from": C.PRODUCTS, "localField": "lic.product_id",
                     "foreignField": "_id", "as": "product"}},
        {"$unwind": "$product"},
        {"$lookup": {"from": C.VENDORS, "localField": "product.vendor_id",
                     "foreignField": "_id", "as": "vendor"}},
        {"$unwind": "$vendor"},
        {"$group": {
            "_id": "$vendor.name",
            "total": {"$sum": "$spend"},
            "currency": {"$first": "$lic.currency"},
        }},
        {"$project": {"_id": 0, "vendor": "$_id", "total": 1, "currency": 1}},
        {"$sort": {"total": -1}},
    ]


def cost_by_cost_center(vendor: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Gasto total por centro de custo.
    Se `vendor` for informado, considera só as licenças daquele fornecedor
    (responde: 'quanto gastamos com o fornecedor Y por centro de custo?').
    """
    return list(get_db()[C.ALLOCATIONS].aggregate(_pipeline_por_centro(vendor)))


def cost_by_vendor() -> List[Dict[str, Any]]:
    """Gasto total por fornecedor (allocations -> licença -> produto -> fornecedor)."""
    return list(get_db()[C.ALLOCATIONS].aggregate(_pipeline_por_fornecedor()))


# ---------------------------------------------------------------------------
# Versões "só o comando" (para o painel "Ver a consulta")
# ---------------------------------------------------------------------------
def consulta_por_centro(vendor: Optional[str] = None) -> str:
    """String mongosh do gasto por centro de custo (o mesmo pipeline que roda)."""
    return mongosh.formatar_aggregate(C.ALLOCATIONS, _pipeline_por_centro(vendor))


def consulta_por_fornecedor() -> str:
    """String mongosh do gasto por fornecedor (o mesmo pipeline que roda)."""
    return mongosh.formatar_aggregate(C.ALLOCATIONS, _pipeline_por_fornecedor())
