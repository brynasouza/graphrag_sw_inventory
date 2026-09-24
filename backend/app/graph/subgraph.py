"""
Subgrafo de uma entidade — o "mini-grafo" que acompanha cada resposta.

Dado o nó de entrada (a licença ou o fornecedor que a busca vetorial achou),
reunimos SÓ as entidades ligadas a ele, no formato canônico {nodes, edges}
(veja graphdata.py). O frontend desenha esse subgrafo ao lado da resposta,
mostrando de onde vieram os fatos.

Como os dados vivem numa coleção auto-referencial (`graph`), um único
`$graphLookup` a partir da licença traz TODOS os nós alcançáveis "para baixo"
(produto/contrato/fornecedor e projeto → time → centro) — e cada nó devolvido já
vem com suas `arestas` embutidas, então NÃO é preciso `$lookup` para hidratar
nada. As arestas de exibição são reconstruídas a partir das `arestas` dos nós
coletados (o GraphBuilder descarta as que ficarem sem uma das pontas).

Os servidores de um projeto entram por travessia REVERSA (a aresta
servidor → projeto sai do servidor, aponta "para baixo" no projeto): achamos os
nós `server` cuja aresta `servidor_projeto` aponta para um projeto alocado.
"""
from typing import Any, Dict, List

from app.graph import graphdata as G
from app.graph.queries import to_object_id
from app.models.schemas import Collections as C
from app.models.schemas import EdgeTypes as E

VAZIO: Dict[str, List[Any]] = {"nodes": [], "edges": []}

# Tipos de NÓ alcançáveis "para baixo" a partir de uma licença. No modelo
# auto-referencial, `restrictSearchWithMatch` filtra o nó-alvo por `tipo` (não a
# aresta) — equivalente aqui, pois cada salto cai num tipo de nó distinto.
_TIPOS_DESCENDENTES = [
    "product", "contract", "vendor", "project", "team", "cost_center",
]


def _coletar_descendentes(
    db, license_ids: List[Any]
) -> Dict[Any, Dict[str, Any]]:
    """
    Todos os nós alcançáveis a partir de um conjunto de licenças (+ os servidores
    dos projetos alocados), indexados por `_id`. Cada nó traz suas `arestas`.
    """
    if not license_ids:
        return {}

    pipeline = [
        {"$match": {"_id": {"$in": license_ids}, "tipo": "license"}},
        {"$graphLookup": {
            "from": C.GRAPH,
            "startWith": "$arestas.to",
            "connectFromField": "arestas.to",
            "connectToField": "_id",
            "as": "descendentes",
            "restrictSearchWithMatch": {"tipo": {"$in": _TIPOS_DESCENDENTES}},
        }},
    ]

    nodes: Dict[Any, Dict[str, Any]] = {}
    project_ids: set = set()
    for doc in db[C.GRAPH].aggregate(pipeline):
        descendentes = doc.pop("descendentes", [])
        nodes[doc["_id"]] = doc            # a própria licença (com suas arestas)
        for n in descendentes:
            nodes[n["_id"]] = n
        # projetos alocados: destino das arestas de alocação da licença.
        for a in doc.get("arestas", []):
            if a.get("tipo") == E.ALOCACAO:
                project_ids.add(a["to"])

    # Servidores dos projetos alocados (travessia reversa: server → projeto).
    if project_ids:
        for s in db[C.GRAPH].find({"tipo": "server", "arestas": {"$elemMatch": {
            "tipo": E.SERVIDOR_PROJETO, "to": {"$in": list(project_ids)}}}}):
            nodes[s["_id"]] = s

    return nodes


def _montar(nodes_por_id: Dict[Any, Dict[str, Any]]) -> Dict[str, Any]:
    """Monta o {nodes, edges} canônico a partir dos nós coletados e suas arestas."""
    b = G.GraphBuilder()
    for n in nodes_por_id.values():
        G.add_node_doc(b, n)
    for n in nodes_por_id.values():
        for a in n.get("arestas", []):
            G.add_edge_doc(b, n["_id"], a)
    return b.result()


def subgraph_for_license(db, license_id: str) -> Dict[str, List[Dict[str, Any]]]:
    """Subgrafo a partir de uma licença — num $graphLookup só (+ servidores)."""
    oid = to_object_id(license_id)
    if oid is None:
        return dict(VAZIO)
    if db[C.GRAPH].find_one({"_id": oid, "tipo": "license"}, {"_id": 1}) is None:
        return dict(VAZIO)
    return _montar(_coletar_descendentes(db, [oid]))


def subgraph_for_vendor(db, vendor_id: str) -> Dict[str, List[Dict[str, Any]]]:
    """Subgrafo a partir de um fornecedor: produtos, contratos e licenças (+downstream)."""
    oid = to_object_id(vendor_id)
    if oid is None:
        return dict(VAZIO)
    vendor = db[C.GRAPH].find_one({"_id": oid, "tipo": "vendor"})
    if vendor is None:
        return dict(VAZIO)

    # Produtos e contratos apontam PARA o fornecedor (arestas *_fornecedor).
    # Travessia reversa: achamos os nós cuja aresta embutida aponta ao fornecedor.
    nodes: Dict[Any, Dict[str, Any]] = {oid: vendor}
    product_ids: List[Any] = []
    for n in db[C.GRAPH].find({"arestas": {"$elemMatch": {
        "tipo": {"$in": [E.PRODUTO_FORNECEDOR, E.CONTRATO_FORNECEDOR]}, "to": oid}}}):
        nodes[n["_id"]] = n
        if n.get("tipo") == "product":
            product_ids.append(n["_id"])

    # Licenças desses produtos (reversa: licença → produto).
    license_ids = [
        lic["_id"] for lic in db[C.GRAPH].find(
            {"tipo": "license", "arestas": {"$elemMatch": {
                "tipo": E.LICENCA_PRODUTO, "to": {"$in": product_ids}}}},
            {"_id": 1})
    ]

    # Toda a vizinhança "para baixo" dessas licenças.
    nodes.update(_coletar_descendentes(db, license_ids))
    return _montar(nodes)
