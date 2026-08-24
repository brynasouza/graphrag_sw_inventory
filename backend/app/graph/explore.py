"""
Grafo inteiro para a página "Explorar Grafo".

Lê as 9 coleções de domínio e monta {nodes, edges} no formato canônico
(veja graphdata.py). As arestas saem dos campos de referência (FK) de
cada documento. `allocations` vira aresta licença → projeto (com a
quantidade no rótulo), não um nó.
"""
from typing import Any, Dict, List

from app.graph import graphdata as G
from app.models.schemas import Collections as C


def full_graph(db) -> Dict[str, List[Dict[str, Any]]]:
    """Devolve o grafo completo do inventário como {nodes, edges}."""
    vendors = list(db[C.VENDORS].find())
    products = list(db[C.PRODUCTS].find())
    contracts = list(db[C.CONTRACTS].find())
    licenses = list(db[C.LICENSES].find())
    allocations = list(db[C.ALLOCATIONS].find())
    projects = list(db[C.PROJECTS].find())
    teams = list(db[C.TEAMS].find())
    cost_centers = list(db[C.COST_CENTERS].find())
    servers = list(db[C.SERVERS].find())

    b = G.GraphBuilder()

    # Nós (um por documento; allocations fica de fora — vira aresta).
    for v in vendors:
        G.add_vendor(b, v)
    for p in products:
        G.add_product(b, p)
    for c in contracts:
        G.add_contract(b, c)
    for l in licenses:
        G.add_license(b, l)
    for pr in projects:
        G.add_project(b, pr)
    for t in teams:
        G.add_team(b, t)
    for cc in cost_centers:
        G.add_cost_center(b, cc)
    for s in servers:
        G.add_server(b, s)

    # Arestas a partir das referências entre coleções.
    for p in products:
        b.add_edge(p["_id"], p.get("vendor_id"), G.REL_FORNECEDOR)
    for c in contracts:
        b.add_edge(c["_id"], c.get("vendor_id"), G.REL_FORNECEDOR)
    for l in licenses:
        b.add_edge(l["_id"], l.get("product_id"), G.REL_PRODUTO)
        b.add_edge(l["_id"], l.get("contract_id"), G.REL_CONTRATO)
    for a in allocations:
        b.add_edge(a.get("license_id"), a.get("project_id"),
                   G.REL_ALOCACAO, str(a.get("quantity")))
    for pr in projects:
        b.add_edge(pr["_id"], pr.get("team_id"), G.REL_TIME)
    for t in teams:
        b.add_edge(t["_id"], t.get("cost_center_id"), G.REL_CENTRO)
    for s in servers:
        b.add_edge(s["_id"], s.get("project_id"), G.REL_PROJETO)

    return b.result()
