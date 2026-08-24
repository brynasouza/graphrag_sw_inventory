"""
Testes da busca vetorial (Etapa 5).

Pré-requisitos para estes testes RODAREM (senão são pulados):
  - VOYAGE_API_KEY preenchida no .env;
  - script `build_embeddings` já rodado;
  - índice 'vector_index' criado no Atlas.

Se a busca não estiver pronta, o endpoint responde 503 e o teste é
PULADO (não falha) — assim o pytest continua verde durante o
desenvolvimento, igual aos outros testes de integração.
"""
import pytest


def _search_or_skip(client, q, **params):
    r = client.get("/search", params={"q": q, **params})
    if r.status_code == 503:
        pytest.skip("Busca vetorial não configurada (chave/índice ausente)")
    assert r.status_code == 200, r.text
    return r.json()


def test_frase_de_virtualizacao_acha_vmware(client):
    """Palavras diferentes das do banco ainda devem achar VMware/vSphere."""
    resultados = _search_or_skip(client, "virtualização de servidores no datacenter")
    assert resultados, "esperava ao menos um resultado"
    nomes = " ".join(f"{r['name']} {r['text']}" for r in resultados).lower()
    assert "vmware" in nomes or "vsphere" in nomes


def test_filtro_por_tipo_licenca(client):
    """Com entity_type=license, só voltam licenças."""
    resultados = _search_or_skip(
        client, "banco de dados Oracle", k=5, entity_type="license"
    )
    assert resultados
    assert all(r["entity_type"] == "license" for r in resultados)


def test_score_ordenado(client):
    """Resultados vêm do mais parecido para o menos parecido."""
    resultados = _search_or_skip(client, "licença Microsoft", k=5)
    scores = [r["score"] for r in resultados]
    assert scores == sorted(scores, reverse=True)
