"""
Grafo inteiro para a página "Explorar Grafo".

Agora que os dados são grafo-nativos, montar a visualização é direto: lemos
`graph_nodes` e `graph_edges` e traduzimos cada documento no formato canônico
{nodes, edges} (veja graphdata.py). A aresta de alocação (`tipo:"alocacao"`)
vira licença → projeto com a quantidade no rótulo — coerente com as demais telas.
"""
from typing import Any, Dict, Optional

from app.graph import graphdata as G
from app.graph import mongosh
from app.models.schemas import Collections as C

# Ordem em que as coleções são lidas em full_graph(). A consulta exibida em
# "Ver a consulta" tem que espelhar exatamente estes find().
_COLECOES_DO_GRAFO = [C.GRAPH_NODES, C.GRAPH_EDGES]

# Teto de documentos lidos POR coleção. A demo tem ~60 nós e ~87 arestas (bem
# abaixo disto), então o default NÃO altera o que se vê hoje — ele só evita que
# um dataset muito maior trave o navegador ao carregar o grafo inteiro. Não é
# paginação: paginar um grafo quebraria arestas. Arestas que sobrarem sem um dos
# extremos (por causa do corte) já são descartadas pelo GraphBuilder.result().
LIMITE_POR_COLECAO = 200


def consulta_do_grafo(limite: Optional[int] = None) -> str:
    """
    String mongosh com os find() que montam o grafo.
    A tela "Explorar Grafo" NÃO usa agregação: lê `graph_nodes` e `graph_edges`
    e monta os nós/arestas em Python. Então o comando honesto a mostrar são
    estes find() — com o mesmo `.limit()` que a execução aplica.
    """
    if limite is None:
        limite = LIMITE_POR_COLECAO
    return mongosh.formatar_finds(_COLECOES_DO_GRAFO, limite)


def full_graph(db, limite: Optional[int] = None) -> Dict[str, Any]:
    """
    Devolve o grafo completo do inventário como {nodes, edges}.

    `graph_nodes` e `graph_edges` são lidas com `.limit(limite)` (default
    LIMITE_POR_COLECAO). Se alguma delas bateu no teto, o grafo pode estar
    parcial: sinalizamos isso em `truncado` para não passar por completo um
    grafo cortado.
    """
    if limite is None:
        limite = LIMITE_POR_COLECAO

    nodes = list(db[C.GRAPH_NODES].find().limit(limite))
    edges = list(db[C.GRAPH_EDGES].find().limit(limite))

    # Bateu no teto em alguma coleção -> pode haver mais dados não carregados.
    truncado = len(nodes) == limite or len(edges) == limite

    b = G.GraphBuilder()
    for n in nodes:
        G.add_node_doc(b, n)
    for e in edges:
        G.add_edge_doc(b, e)

    return {**b.result(), "truncado": truncado, "limite": limite}
