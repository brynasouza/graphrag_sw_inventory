"""
Testes dos índices da coleção auto-referencial `graph`.

Dois índices sustentam a demo:
  - `props.expires_at`: a tela de alertas filtra (`$lte`) e ordena (`sort`)
    licenças por data de expiração. Sem ele, cada consulta varre a coleção.
  - `arestas.to` (multikey): é o `connectToField` do `$graphLookup` no sentido
    direto e o alvo do `$elemMatch` nas travessias reversas (servidores,
    fornecedor). Sem ele, cada salto vira COLLSCAN.

`ensure_indexes` é idempotente, então chamá-lo aqui e conferir o resultado não
tem efeito colateral no banco da demo.
"""
from app.core.db import get_db
from app.core.indexes import ensure_indexes
from app.models.schemas import Collections as C


def _campos_indexados(db):
    return {
        tuple(campo for campo, _ in info["key"])
        for info in db[C.GRAPH].index_information().values()
    }


def test_indice_expires_at_existe(client):
    db = get_db()
    ensure_indexes(db)  # idempotente
    assert ("props.expires_at",) in _campos_indexados(db), \
        "esperava índice em graph.props.expires_at (tela de alertas filtra/ordena por ele)"


def test_indice_arestas_to_existe(client):
    db = get_db()
    ensure_indexes(db)  # idempotente
    assert ("arestas.to",) in _campos_indexados(db), \
        "esperava índice multikey em graph.arestas.to (connectToField do $graphLookup e $elemMatch reverso)"
