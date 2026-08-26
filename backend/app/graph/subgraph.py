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


# ---------------------------------------------------------------------------
# Subgrafo da LICENÇA numa AGREGAÇÃO SÓ (uma ida ao banco, não ~15).
#
# Antes, o subgrafo da licença fazia um laço Python aninhado com um find_one
# por alocação -> projeto -> time -> centro -> servidores: dezenas de idas e
# voltas SEQUENCIAIS à rede, que dominavam o tempo do /ask. Aqui trazemos toda
# a vizinhança da licença em UM pipeline com $lookup aninhado; depois montamos
# o {nodes, edges} em Python puro (custo zero de rede). O resultado tem os
# MESMOS nós, arestas e props de antes.
#
# Usamos a forma `let` + `pipeline` + `$expr` nos $lookup aninhados (funciona
# em qualquer versão), com preserveNullAndEmptyArrays para não perder a licença
# caso algum vínculo (produto, contrato…) esteja ausente.
# ---------------------------------------------------------------------------
def _pipeline_subgrafo_licenca(oid) -> List[Dict[str, Any]]:
    return [
        {"$match": {"_id": oid}},
        # licença -> produto -> fornecedor
        {"$lookup": {
            "from": C.PRODUCTS,
            "let": {"pid": "$product_id"},
            "pipeline": [
                {"$match": {"$expr": {"$eq": ["$_id", "$$pid"]}}},
                {"$lookup": {"from": C.VENDORS, "localField": "vendor_id",
                             "foreignField": "_id", "as": "vendor"}},
                {"$unwind": {"path": "$vendor", "preserveNullAndEmptyArrays": True}},
            ],
            "as": "product",
        }},
        {"$unwind": {"path": "$product", "preserveNullAndEmptyArrays": True}},
        # licença -> contrato
        {"$lookup": {"from": C.CONTRACTS, "localField": "contract_id",
                     "foreignField": "_id", "as": "contract"}},
        {"$unwind": {"path": "$contract", "preserveNullAndEmptyArrays": True}},
        # licença -> alocações -> (projeto -> time -> centro) + servidores do projeto
        {"$lookup": {
            "from": C.ALLOCATIONS,
            "let": {"lid": "$_id"},
            "pipeline": [
                {"$match": {"$expr": {"$eq": ["$license_id", "$$lid"]}}},
                {"$lookup": {
                    "from": C.PROJECTS,
                    "let": {"prid": "$project_id"},
                    "pipeline": [
                        {"$match": {"$expr": {"$eq": ["$_id", "$$prid"]}}},
                        {"$lookup": {
                            "from": C.TEAMS,
                            "let": {"tid": "$team_id"},
                            "pipeline": [
                                {"$match": {"$expr": {"$eq": ["$_id", "$$tid"]}}},
                                {"$lookup": {"from": C.COST_CENTERS,
                                             "localField": "cost_center_id",
                                             "foreignField": "_id", "as": "cost_center"}},
                                {"$unwind": {"path": "$cost_center",
                                             "preserveNullAndEmptyArrays": True}},
                            ],
                            "as": "team",
                        }},
                        {"$unwind": {"path": "$team", "preserveNullAndEmptyArrays": True}},
                        {"$lookup": {"from": C.SERVERS, "localField": "_id",
                                     "foreignField": "project_id", "as": "servers"}},
                    ],
                    "as": "project",
                }},
                {"$unwind": {"path": "$project", "preserveNullAndEmptyArrays": True}},
            ],
            "as": "allocations",
        }},
    ]


def _montar_subgrafo_licenca(b: G.GraphBuilder, lic: Dict[str, Any]) -> None:
    """Monta nós/arestas a partir do documento único devolvido pela agregação."""
    G.add_license(b, lic)

    prod = lic.get("product")
    if prod:
        G.add_product(b, prod)
        b.add_edge(lic["_id"], prod["_id"], G.REL_PRODUTO)
        vend = prod.get("vendor")
        if vend:
            G.add_vendor(b, vend)
            b.add_edge(prod["_id"], vend["_id"], G.REL_FORNECEDOR)

    contr = lic.get("contract")
    if contr:
        G.add_contract(b, contr)
        b.add_edge(lic["_id"], contr["_id"], G.REL_CONTRATO)

    for a in lic.get("allocations", []):
        proj = a.get("project")
        if not proj:
            continue
        # projeto -> time -> centro de custo
        G.add_project(b, proj)
        team = proj.get("team")
        if team:
            G.add_team(b, team)
            b.add_edge(proj["_id"], team["_id"], G.REL_TIME)
            cc = team.get("cost_center")
            if cc:
                G.add_cost_center(b, cc)
                b.add_edge(team["_id"], cc["_id"], G.REL_CENTRO)
        # servidores do projeto
        for s in proj.get("servers", []):
            G.add_server(b, s)
            b.add_edge(s["_id"], proj["_id"], G.REL_PROJETO)
        # licença -> projeto (via allocation), rótulo = quantidade
        b.add_edge(lic["_id"], proj["_id"], G.REL_ALOCACAO, str(a.get("quantity")))


def subgraph_for_license(db, license_id: str) -> Dict[str, List[Dict[str, Any]]]:
    """Subgrafo a partir de uma licença — numa agregação só."""
    oid = to_object_id(license_id)
    if oid is None:
        return dict(VAZIO)
    docs = list(db[C.LICENSES].aggregate(_pipeline_subgrafo_licenca(oid)))
    if not docs:
        return dict(VAZIO)
    b = G.GraphBuilder()
    _montar_subgrafo_licenca(b, docs[0])
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
