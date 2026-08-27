"""
Teste do índice de `expires_at` (ponto 2 dos ajustes de performance).

A tela de alertas filtra (`$lte`) e ordena (`sort`) licenças por data de
expiração. Sem índice nesse campo, cada consulta varre a coleção inteira.
`ensure_indexes` é idempotente, então chamá-lo aqui e conferir o resultado
não tem efeito colateral no banco da demo.
"""
from app.core.db import get_db
from app.core.indexes import ensure_indexes


def test_indice_expires_at_existe(client):
    db = get_db()
    ensure_indexes(db)  # idempotente
    campos = {
        tuple(campo for campo, _ in info["key"])
        for info in db["licenses"].index_information().values()
    }
    assert ("expires_at",) in campos, \
        "esperava índice em licenses.expires_at (tela de alertas filtra/ordena por ele)"
