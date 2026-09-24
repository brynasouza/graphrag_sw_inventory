"""
Grafo inteiro para a página "Explorar Grafo".

Agora que os dados vivem numa coleção auto-referencial (`graph`), montar a
visualização é direto: lemos os documentos e traduzimos cada nó + suas `arestas`
embutidas no formato canônico {nodes, edges} (veja graphdata.py). A aresta de
alocação (`tipo:"alocacao"`) vira licença → projeto com a quantidade no rótulo —
coerente com as demais telas.
"""
from typing import Any, Dict, Optional

from app.graph import graphdata as G
from app.graph import mongosh
from app.models.schemas import Collections as C

# Teto de documentos lidos. A demo tem ~60 nós (bem abaixo disto), então o
# default NÃO altera o que se vê hoje — ele só evita que um dataset muito maior
# trave o navegador ao carregar o grafo inteiro. Não é paginação: paginar um
# grafo quebraria arestas. Arestas que sobrarem sem um dos extremos (por causa
# do corte) já são descartadas pelo GraphBuilder.result().
LIMITE_POR_COLECAO = 200


def consulta_do_grafo(limite: Optional[int] = None) -> str:
    """
    String mongosh com o find() que monta o grafo.
    A tela "Explorar Grafo" NÃO usa agregação: lê a coleção `graph` e monta os
    nós/arestas (das `arestas` embutidas) em Python. Então o comando honesto a
    mostrar é este único find() — com o mesmo `.limit()` que a execução aplica.
    """
    if limite is None:
        limite = LIMITE_POR_COLECAO
    return mongosh.formatar_find(C.GRAPH, {}, limite=limite)


def full_graph(db, limite: Optional[int] = None) -> Dict[str, Any]:
    """
    Devolve o grafo completo do inventário como {nodes, edges}.

    A coleção `graph` é lida com `.limit(limite)` (default LIMITE_POR_COLECAO).
    Se bateu no teto, o grafo pode estar parcial: sinalizamos isso em `truncado`
    para não passar por completo um grafo cortado.
    """
    if limite is None:
        limite = LIMITE_POR_COLECAO

    nodes = list(db[C.GRAPH].find().limit(limite))

    # Bateu no teto -> pode haver mais dados não carregados.
    truncado = len(nodes) == limite

    b = G.GraphBuilder()
    for n in nodes:
        G.add_node_doc(b, n)
    for n in nodes:
        for a in n.get("arestas", []):
            G.add_edge_doc(b, n["_id"], a)

    return {**b.result(), "truncado": truncado, "limite": limite}
