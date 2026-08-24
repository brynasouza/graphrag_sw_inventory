"""
Subgrafo de uma entidade — o "mini-grafo" que acompanha cada resposta.

Dado o nó de entrada (a licença ou o fornecedor que a busca vetorial
achou), reunimos SÓ as entidades ligadas a ele, no formato canônico
{nodes, edges} (veja graphdata.py). O frontend desenha esse subgrafo ao
lado da resposta, mostrando de onde vieram os fatos.

Reaproveita `to_object_id` de queries.py e os ajudantes de graphdata.py.
"""
from typing import Any, Dict, List

from app.graph import graphdata as G
from app.graph.queries import to_object_id
from app.models.schemas import Collections as C

VAZIO: Dict[str, List[Any]] = {"nodes": [], "edges": []}


def _expand_project(db, b: G.GraphBuilder, proj: Dict[str, Any]) -> None:
    """Projeto -> time -> centro de custo, e os servidores do projeto."""
    G.add_project(b, proj)
    team = db[C.TEAMS].find_one({"_id": proj.get("team_id")})
    if team:
        G.add_team(b, team)
        b.add_edge(proj["_id"], team["_id"], G.REL_TIME)
        cc = db[C.COST_CENTERS].find_one({"_id": team.get("cost_center_id")})
        if cc:
            G.add_cost_center(b, cc)
            b.add_edge(team["_id"], cc["_id"], G.REL_CENTRO)
    for s in db[C.SERVERS].find({"project_id": proj["_id"]}):
        G.add_server(b, s)
        b.add_edge(s["_id"], proj["_id"], G.REL_PROJETO)


def _expand_license(db, b: G.GraphBuilder, lic: Dict[str, Any]) -> None:
    """Licença + produto/fornecedor/contrato + projetos alocados (downstream)."""
    G.add_license(b, lic)

    prod = db[C.PRODUCTS].find_one({"_id": lic.get("product_id")})
    if prod:
        G.add_product(b, prod)
        b.add_edge(lic["_id"], prod["_id"], G.REL_PRODUTO)
        vend = db[C.VENDORS].find_one({"_id": prod.get("vendor_id")})
        if vend:
            G.add_vendor(b, vend)
            b.add_edge(prod["_id"], vend["_id"], G.REL_FORNECEDOR)

    contr = db[C.CONTRACTS].find_one({"_id": lic.get("contract_id")})
    if contr:
        G.add_contract(b, contr)
        b.add_edge(lic["_id"], contr["_id"], G.REL_CONTRATO)

    for a in db[C.ALLOCATIONS].find({"license_id": lic["_id"]}):
        proj = db[C.PROJECTS].find_one({"_id": a.get("project_id")})
        if not proj:
            continue
        _expand_project(db, b, proj)
        b.add_edge(lic["_id"], proj["_id"], G.REL_ALOCACAO, str(a.get("quantity")))


def subgraph_for_license(db, license_id: str) -> Dict[str, List[Dict[str, Any]]]:
    """Subgrafo a partir de uma licença."""
    oid = to_object_id(license_id)
    if oid is None:
        return dict(VAZIO)
    lic = db[C.LICENSES].find_one({"_id": oid})
    if lic is None:
        return dict(VAZIO)
    b = G.GraphBuilder()
    _expand_license(db, b, lic)
    return b.result()


def subgraph_for_vendor(db, vendor_id: str) -> Dict[str, List[Dict[str, Any]]]:
    """Subgrafo a partir de um fornecedor: produtos, contratos e licenças (+downstream)."""
    oid = to_object_id(vendor_id)
    if oid is None:
        return dict(VAZIO)
    vend = db[C.VENDORS].find_one({"_id": oid})
    if vend is None:
        return dict(VAZIO)

    b = G.GraphBuilder()
    G.add_vendor(b, vend)

    for contr in db[C.CONTRACTS].find({"vendor_id": vend["_id"]}):
        G.add_contract(b, contr)
        b.add_edge(contr["_id"], vend["_id"], G.REL_FORNECEDOR)

    prods = list(db[C.PRODUCTS].find({"vendor_id": vend["_id"]}))
    prod_ids = [p["_id"] for p in prods]
    for p in prods:
        G.add_product(b, p)
        b.add_edge(p["_id"], vend["_id"], G.REL_FORNECEDOR)

    for lic in db[C.LICENSES].find({"product_id": {"$in": prod_ids}}):
        _expand_license(db, b, lic)

    return b.result()
