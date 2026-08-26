"""
Rotas HTTP para a travessia de grafo (Etapa 3).

Estas rotas respondem de forma DETERMINÍSTICA (sem IA): seguem as
referências entre coleções e devolvem os fatos exatos.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pymongo.errors import PyMongoError

from app.core.db import get_db
from app.graph import costs, explore, queries, subgraph

router = APIRouter(prefix="/graph", tags=["grafo"])


@router.get("/licenses")
def get_licenses(
    expiring_in_days: Optional[int] = Query(None, ge=0),
    incluir_consulta: bool = Query(False),
):
    """
    Lista licenças. Passe ?expiring_in_days=90 para ver só as que
    vencem nos próximos 90 dias (útil para achar o 'X' das perguntas).

    Com ?incluir_consulta=true, devolve {dados, consulta} com o find() real.
    Sem o parâmetro, a resposta é idêntica à de sempre.
    """
    dados = queries.list_licenses(expiring_in_days)
    if incluir_consulta:
        return {"dados": dados, "consulta": queries.consulta_licencas(expiring_in_days)}
    return dados


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
def get_cost_by_cost_center(
    vendor: Optional[str] = Query(None),
    incluir_consulta: bool = Query(False),
):
    """
    Gasto por centro de custo. Passe ?vendor=VMware para responder
    'quanto gastamos com o fornecedor Y por centro de custo?'.

    Com ?incluir_consulta=true, devolve {dados, consulta} — a `consulta` é o
    comando MongoDB real (para o painel "Ver a consulta"). Sem o parâmetro, a
    resposta é idêntica à de sempre.
    """
    dados = costs.cost_by_cost_center(vendor)
    if incluir_consulta:
        return {"dados": dados, "consulta": costs.consulta_por_centro(vendor)}
    return dados


@router.get("/costs/by-vendor")
def get_cost_by_vendor(incluir_consulta: bool = Query(False)):
    """
    Gasto total por fornecedor.

    Com ?incluir_consulta=true, devolve {dados, consulta} com o comando
    MongoDB real. Sem o parâmetro, a resposta é idêntica à de sempre.
    """
    dados = costs.cost_by_vendor()
    if incluir_consulta:
        return {"dados": dados, "consulta": costs.consulta_por_fornecedor()}
    return dados


# ---------------------------------------------------------------------------
# Visualização de grafo (nós + arestas) para o frontend
# ---------------------------------------------------------------------------
@router.get("/explore")
def get_full_graph(incluir_consulta: bool = Query(False)):
    """
    Grafo inteiro do inventário como {nodes, edges}, para a página
    'Explorar Grafo'. Nós coloridos por tipo; allocations viram arestas
    licença → projeto (com a quantidade no rótulo).

    Com ?incluir_consulta=true, devolve {dados, consulta} — a `consulta` são os
    find() reais que montam o grafo (esta tela não usa $lookup). Sem o
    parâmetro, a resposta é idêntica à de sempre.
    """
    try:
        dados = explore.full_graph(get_db())
        if incluir_consulta:
            return {"dados": dados, "consulta": explore.consulta_do_grafo()}
        return dados
    except PyMongoError as exc:
        raise HTTPException(
            status_code=503,
            detail="Banco indisponível ao montar o grafo. Detalhe: " + str(exc),
        )


@router.get("/licenses/{license_id}/subgraph")
def get_license_subgraph(license_id: str):
    """Subgrafo (mini-grafo) a partir de uma licença."""
    try:
        return subgraph.subgraph_for_license(get_db(), license_id)
    except PyMongoError as exc:
        raise HTTPException(
            status_code=503,
            detail="Banco indisponível ao montar o subgrafo. Detalhe: " + str(exc),
        )


@router.get("/vendors/{vendor_id}/subgraph")
def get_vendor_subgraph(vendor_id: str):
    """Subgrafo (mini-grafo) a partir de um fornecedor."""
    try:
        return subgraph.subgraph_for_vendor(get_db(), vendor_id)
    except PyMongoError as exc:
        raise HTTPException(
            status_code=503,
            detail="Banco indisponível ao montar o subgrafo. Detalhe: " + str(exc),
        )
