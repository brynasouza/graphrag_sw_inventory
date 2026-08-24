"""
Rotas HTTP para a travessia de grafo (Etapa 3).

Estas rotas respondem de forma DETERMINÍSTICA (sem IA): seguem as
referências entre coleções e devolvem os fatos exatos.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.graph import costs, queries

router = APIRouter(prefix="/graph", tags=["grafo"])


@router.get("/licenses")
def get_licenses(expiring_in_days: Optional[int] = Query(None, ge=0)):
    """
    Lista licenças. Passe ?expiring_in_days=90 para ver só as que
    vencem nos próximos 90 dias (útil para achar o 'X' das perguntas).
    """
    return queries.list_licenses(expiring_in_days)


@router.get("/licenses/{license_id}/projects")
def get_projects_using_license(license_id: str):
    """'Quais projetos usam a licença X?'"""
    return queries.projects_using_license(license_id)


@router.get("/licenses/{license_id}/impact")
def get_license_impact(license_id: str):
    """'Se a licença X expirar, quais times/projetos/centros são impactados?'"""
    resultado = queries.license_impact(license_id)
    if resultado is None:
        raise HTTPException(status_code=404, detail="Licença não encontrada")
    return resultado


@router.get("/costs/by-cost-center")
def get_cost_by_cost_center(vendor: Optional[str] = Query(None)):
    """
    Gasto por centro de custo. Passe ?vendor=VMware para responder
    'quanto gastamos com o fornecedor Y por centro de custo?'.
    """
    return costs.cost_by_cost_center(vendor)


@router.get("/costs/by-vendor")
def get_cost_by_vendor():
    """Gasto total por fornecedor."""
    return costs.cost_by_vendor()
