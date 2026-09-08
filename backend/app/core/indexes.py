"""
Índices das coleções grafo — para o `$graphLookup` e os `$match`/`find` não
varrerem tudo.

Por que isto existe:
A travessia com `$graphLookup` recursa em `graph_edges` casando
`connectToField:"from"` a cada salto — ou seja, faz uma busca por `from` para
cada nó alcançado. Sem índice em `from`, cada salto é uma VARREDURA da coleção
de arestas. As agregações e os subgrafos também filtram arestas por `to` e por
`tipo`, e a tela de alertas filtra/ordena nós de licença por `props.expires_at`.
No tamanho de demo o custo é pequeno, mas numa demo enterprise o `explain()`
mostrando "COLLSCAN" tira credibilidade. Com índice, cada salto vira uma busca
direta (IXSCAN).

O campo `_id` já é indexado automaticamente pelo MongoDB, então só criamos
índice nos campos pelos quais consultamos: as pontas das arestas (`from`/`to`),
o tipo (de nó e de aresta) e a data de expiração das licenças.

`create_index` é idempotente: se o índice já existe com a mesma definição, a
chamada é um no-op barato. Por isso é seguro rodar isto a cada startup e no seed.
"""
from typing import List, Tuple

from pymongo.database import Database

from app.models.schemas import Collections as C

# (coleção, campo) — os campos pelos quais a travessia/agregações consultam.
_INDICES: List[Tuple[str, str]] = [
    (C.GRAPH_EDGES, "from"),          # cada salto do $graphLookup casa por `from`
    (C.GRAPH_EDGES, "to"),            # agregações e subgrafo filtram por destino
    (C.GRAPH_EDGES, "tipo"),          # restringe as arestas por tipo de relação
    (C.GRAPH_NODES, "tipo"),          # lista/monta o grafo por tipo de entidade
    (C.GRAPH_NODES, "props.expires_at"),  # tela de alertas filtra e ordena por expiração
]


def ensure_indexes(db: Database) -> List[str]:
    """
    Cria (se ainda não existirem) os índices do grafo.
    Idempotente: pode ser chamado no startup e no seed sem efeito colateral.
    Devolve a lista de nomes de índice garantidos (útil para log/teste).
    """
    criados: List[str] = []
    for colecao, campo in _INDICES:
        nome = db[colecao].create_index(campo)  # no-op se já existe
        criados.append(f"{colecao}.{nome}")
    return criados
