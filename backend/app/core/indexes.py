"""
Índices da coleção `graph` — para o `$graphLookup` e os `$match`/`find` não
varrerem tudo.

Por que isto existe:
A travessia com `$graphLookup` recursa na coleção `graph` casando
`connectToField:"_id"` a cada salto no sentido "para baixo" (e
`connectToField:"arestas.to"` no sentido reverso). O `_id` já é indexado
automaticamente, mas `arestas.to` não — sem índice nele, a travessia reversa e
o casamento por destino viram VARREDURA. As agregações/subgrafos também partem
de `tipo`, e a tela de alertas filtra/ordena licenças por `props.expires_at`.
No tamanho de demo o custo é pequeno, mas numa demo enterprise o `explain()`
mostrando "COLLSCAN" tira credibilidade. Com índice, cada salto vira IXSCAN.

Como as arestas agora vivem embutidas no nó (`arestas: [{to, tipo, props}]`),
`arestas.to` e `arestas.tipo` são índices MULTIKEY (um valor por elemento do
array). O `_id` é auto-indexado, então só criamos índice nos campos pelos quais
consultamos.

`create_index` é idempotente: se o índice já existe com a mesma definição, a
chamada é um no-op barato. Por isso é seguro rodar isto a cada startup e no seed.
"""
from typing import List, Tuple

from pymongo.database import Database

from app.models.schemas import Collections as C

# (coleção, campo) — os campos pelos quais a travessia/agregações consultam.
_INDICES: List[Tuple[str, str]] = [
    (C.GRAPH, "tipo"),               # lista/monta o grafo por tipo de entidade
    (C.GRAPH, "props.expires_at"),   # tela de alertas filtra e ordena por expiração
    (C.GRAPH, "arestas.to"),         # $graphLookup (reverso) e casamento por destino
    (C.GRAPH, "arestas.tipo"),       # restringe/filtra arestas por tipo de relação
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
