"""
Subgrafo de uma entidade — o "mini-grafo" que acompanha cada resposta.

Dado o nó de entrada (a licença ou o fornecedor que a busca vetorial achou),
reunimos SÓ as entidades ligadas a ele, no formato canônico {nodes, edges}
(veja graphdata.py). O frontend desenha esse subgrafo ao lado da resposta,
mostrando de onde vieram os fatos.

Como os dados já são grafo, um único `$graphLookup` a partir do nó traz TODAS as
arestas alcançáveis "para baixo" (licença → produto/contrato/fornecedor e
licença → projeto → time → centro). Os servidores de um projeto entram à parte,
porque a aresta servidor → projeto aponta na direção contrária (o servidor é
"pai" do projeto no sentido da alocação). Depois carregamos os nós citados e
montamos o {nodes, edges} em Python.
"""
from typing import Any, Dict, List, Set, Tuple

from app.graph import graphdata as G
from app.graph.queries import to_object_id
from app.models.schemas import Collections as C
from app.models.schemas import EdgeTypes as E

VAZIO: Dict[str, List[Any]] = {"nodes": [], "edges": []}

# Arestas percorríveis "para baixo" a partir de uma licença.
_DESCENDENTES = [
    E.ALOCACAO, E.LICENCA_PRODUTO, E.LICENCA_CONTRATO,
    E.PRODUTO_FORNECEDOR, E.CONTRATO_FORNECEDOR,
    E.PROJETO_TIME, E.TIME_CENTRO,
]


def _descendentes_de_licencas(
    db, license_ids: List[Any]
) -> Tuple[List[Dict[str, Any]], Set[Any]]:
    """
    Todas as arestas alcançáveis a partir de um conjunto de licenças (+ os
    servidores dos projetos alocados). Devolve (arestas, ids_de_nós).
    """
    if not license_ids:
        return [], set()

    pipeline = [
        {"$match": {"_id": {"$in": license_ids}, "tipo": "license"}},
        {"$graphLookup": {
            "from": C.GRAPH_EDGES,
            "startWith": "$_id",
            "connectFromField": "to",
            "connectToField": "from",
            "as": "caminho",
            "restrictSearchWithMatch": {"tipo": {"$in": _DESCENDENTES}},
        }},
        {"$project": {"caminho": 1}},
    ]

    arestas: List[Dict[str, Any]] = []
    node_ids: Set[Any] = set(license_ids)
    project_ids: Set[Any] = set()
    for doc in db[C.GRAPH_NODES].aggregate(pipeline):
        for e in doc.get("caminho", []):
            arestas.append(e)
            node_ids.add(e["from"])
            node_ids.add(e["to"])
            if e["tipo"] == E.ALOCACAO:
                project_ids.add(e["to"])

    # Servidores dos projetos alocados (aresta servidor → projeto).
    if project_ids:
        for e in db[C.GRAPH_EDGES].find(
            {"tipo": E.SERVIDOR_PROJETO, "to": {"$in": list(project_ids)}}
        ):
            arestas.append(e)
            node_ids.add(e["from"])
            node_ids.add(e["to"])

    return arestas, node_ids


def _montar(db, arestas: List[Dict[str, Any]], node_ids: Set[Any]) -> Dict[str, Any]:
    """Carrega os nós citados e monta o {nodes, edges} canônico."""
    b = G.GraphBuilder()
    for n in db[C.GRAPH_NODES].find({"_id": {"$in": list(node_ids)}}):
        G.add_node_doc(b, n)
    for e in arestas:
        G.add_edge_doc(b, e)
    return b.result()


def subgraph_for_license(db, license_id: str) -> Dict[str, List[Dict[str, Any]]]:
    """Subgrafo a partir de uma licença — num $graphLookup só (+ servidores)."""
    oid = to_object_id(license_id)
    if oid is None:
        return dict(VAZIO)
    if db[C.GRAPH_NODES].find_one({"_id": oid, "tipo": "license"}, {"_id": 1}) is None:
        return dict(VAZIO)
    arestas, node_ids = _descendentes_de_licencas(db, [oid])
    return _montar(db, arestas, node_ids)


def subgraph_for_vendor(db, vendor_id: str) -> Dict[str, List[Dict[str, Any]]]:
    """Subgrafo a partir de um fornecedor: produtos, contratos e licenças (+downstream)."""
    oid = to_object_id(vendor_id)
    if oid is None:
        return dict(VAZIO)
    if db[C.GRAPH_NODES].find_one({"_id": oid, "tipo": "vendor"}, {"_id": 1}) is None:
        return dict(VAZIO)

    # Produtos e contratos apontam PARA o fornecedor (arestas *_fornecedor).
    arestas: List[Dict[str, Any]] = []
    node_ids: Set[Any] = {oid}
    product_ids: List[Any] = []
    for e in db[C.GRAPH_EDGES].find(
        {"to": oid, "tipo": {"$in": [E.PRODUTO_FORNECEDOR, E.CONTRATO_FORNECEDOR]}}
    ):
        arestas.append(e)
        node_ids.add(e["from"])
        if e["tipo"] == E.PRODUTO_FORNECEDOR:
            product_ids.append(e["from"])

    # Licenças desses produtos (aresta licença → produto).
    license_ids = [
        e["from"] for e in db[C.GRAPH_EDGES].find(
            {"tipo": E.LICENCA_PRODUTO, "to": {"$in": product_ids}}, {"from": 1})
    ]

    # Toda a vizinhança "para baixo" dessas licenças.
    ar_lic, ids_lic = _descendentes_de_licencas(db, license_ids)
    arestas += ar_lic
    node_ids |= ids_lic

    return _montar(db, arestas, node_ids)
