"""
Grafo inteiro para a página "Explorar Grafo".

Lê as 9 coleções de domínio e monta {nodes, edges} no formato canônico
(veja graphdata.py). As arestas saem dos campos de referência (FK) de
cada documento. `allocations` vira aresta licença → projeto (com a
quantidade no rótulo), não um nó.
"""
from typing import Any, Dict, List, Optional

from app.graph import graphdata as G
from app.graph import mongosh
from app.models.schemas import Collections as C

# Ordem em que as coleções são lidas em full_graph(). A consulta exibida em
# "Ver a consulta" tem que espelhar exatamente estes find().
_COLECOES_DO_GRAFO = [
    C.VENDORS, C.PRODUCTS, C.CONTRACTS, C.LICENSES, C.ALLOCATIONS,
    C.PROJECTS, C.TEAMS, C.COST_CENTERS, C.SERVERS,
]

# Teto de documentos lidos POR coleção. A demo tem ~60 nós no total (cada
# coleção bem abaixo disto), então o default NÃO altera o que se vê hoje — ele
# só evita que um dataset muito maior trave o navegador ao carregar o grafo
# inteiro. Não é paginação: paginar um grafo quebraria arestas. Arestas que
# sobrarem sem um dos extremos (por causa do corte) já são descartadas pelo
# GraphBuilder.result(), então o grafo continua íntegro.
LIMITE_POR_COLECAO = 200


def consulta_do_grafo(limite: Optional[int] = None) -> str:
    """
    String mongosh com os find() que montam o grafo.
    A tela "Explorar Grafo" NÃO usa $lookup: lê as 9 coleções e monta os
    nós/arestas em Python. Então o comando honesto a mostrar são estes find()
    — com o mesmo `.limit()` que a execução aplica.
    """
    if limite is None:
        limite = LIMITE_POR_COLECAO
    return mongosh.formatar_finds(_COLECOES_DO_GRAFO, limite)


def full_graph(db, limite: Optional[int] = None) -> Dict[str, Any]:
    """
    Devolve o grafo completo do inventário como {nodes, edges}.

    Cada coleção é lida com `.limit(limite)` (default LIMITE_POR_COLECAO). Se
    alguma coleção bateu no teto, o grafo pode estar parcial: sinalizamos isso
    em `truncado` para não passar por completo um grafo cortado.
    """
    if limite is None:
        limite = LIMITE_POR_COLECAO

    vendors = list(db[C.VENDORS].find().limit(limite))
    products = list(db[C.PRODUCTS].find().limit(limite))
    contracts = list(db[C.CONTRACTS].find().limit(limite))
    licenses = list(db[C.LICENSES].find().limit(limite))
    allocations = list(db[C.ALLOCATIONS].find().limit(limite))
    projects = list(db[C.PROJECTS].find().limit(limite))
    teams = list(db[C.TEAMS].find().limit(limite))
    cost_centers = list(db[C.COST_CENTERS].find().limit(limite))
    servers = list(db[C.SERVERS].find().limit(limite))

    # Bateu no teto em alguma coleção -> pode haver mais dados não carregados.
    truncado = any(len(docs) == limite for docs in (
        vendors, products, contracts, licenses, allocations,
        projects, teams, cost_centers, servers))

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

    return {**b.result(), "truncado": truncado, "limite": limite}
