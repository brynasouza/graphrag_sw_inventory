"""
Testes do build_embeddings INCREMENTAL (ponto 5 do plano de integridade).

Critério de aceite central: rodar `build` duas vezes seguidas NÃO consome cota
da Voyage na 2ª execução (nada mudou -> nenhum embedding gerado).

Nenhum teste chama a Voyage de verdade: os unitários testam as funções puras
(`_diff`, `_validar_dim`) sem banco, e a integração leve usa um `embed_documents`
falso (conta chamadas) contra uma coleção TEMPORÁRIA — o índice real da demo
nunca é tocado.
"""
import pytest

from app.core.db import get_db
from app.ingestion import build_embeddings as be
from app.retrieval import embeddings

DIM = embeddings.DIM


def _vec():
    return [0.1] * DIM


# --- Unitários puros (sem banco, sem Voyage) --------------------------------
def test_diff_classifica_inalterado_novo_e_orfao():
    desejados = [
        {"entity_type": "license", "entity_id": 1, "name": "A", "text": "t1"},       # inalterado
        {"entity_type": "license", "entity_id": 2, "name": "B", "text": "t2-novo"},  # mudou
        {"entity_type": "vendor", "entity_id": 3, "name": "C", "text": "t3"},        # novo
    ]
    existentes = {
        ("license", 1): {"text": "t1", "embedding": _vec()},
        ("license", 2): {"text": "t2-antigo", "embedding": _vec()},
        ("vendor", 9): {"text": "sumiu", "embedding": _vec()},  # órfão
    }
    a_gerar, reaproveitados, orfaos = be._diff(desejados, existentes)
    assert {d["entity_id"] for d in a_gerar} == {2, 3}
    assert {d["entity_id"] for d in reaproveitados} == {1}
    assert reaproveitados[0]["embedding"] == _vec()  # vetor antigo foi reaproveitado
    assert orfaos == [("vendor", 9)]


def test_diff_regenera_quando_dimensao_gravada_e_invalida():
    desejados = [{"entity_type": "license", "entity_id": 1, "name": "A", "text": "t1"}]
    existentes = {("license", 1): {"text": "t1", "embedding": [0.1, 0.2]}}  # dim errada
    a_gerar, reaproveitados, orfaos = be._diff(desejados, existentes)
    assert len(a_gerar) == 1 and reaproveitados == []  # não confia num vetor torto


def test_validar_dim():
    with pytest.raises(ValueError):
        be._validar_dim([0.1, 0.2])       # dimensão errada -> aborta
    be._validar_dim(_vec())                # dimensão certa -> passa


# --- Integração leve: idempotência sem gastar cota --------------------------
def test_build_nao_regasta_voyage_na_segunda_rodada(client, monkeypatch):
    db = get_db()
    col = db["search_index_teste_tmp"]
    col.delete_many({})

    chamadas = {"textos": 0}

    def fake_embed(textos):
        chamadas["textos"] += len(textos)
        return [_vec() for _ in textos]

    monkeypatch.setattr(embeddings, "embed_documents", fake_embed)
    try:
        be.build(col=col)                 # 1ª: embedda tudo
        primeira = chamadas["textos"]
        assert primeira > 0, "esperava embeddar as entidades na 1ª rodada (rode o seed)"

        be.build(col=col)                 # 2ª: nada mudou
        assert chamadas["textos"] == primeira, "2ª rodada NÃO pode embeddar nada"
    finally:
        col.drop()


def test_build_remove_orfao(client, monkeypatch):
    db = get_db()
    col = db["search_index_teste_tmp2"]
    col.delete_many({})
    monkeypatch.setattr(embeddings, "embed_documents",
                        lambda textos: [_vec() for _ in textos])
    try:
        be.build(col=col)
        col.insert_one({"entity_type": "license", "entity_id": "orfao-inexistente",
                        "name": "x", "text": "x", "embedding": _vec()})
        assert col.count_documents({"entity_id": "orfao-inexistente"}) == 1

        be.build(col=col)  # a entidade órfã não está nos desejados -> some
        assert col.count_documents({"entity_id": "orfao-inexistente"}) == 0
    finally:
        col.drop()
