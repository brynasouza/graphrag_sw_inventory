"""
Testes do GraphRAG completo (Etapa 6) — as 3 perguntas do enunciado.

Estes testes fazem chamadas REAIS ao Claude e à Voyage, então são mais
lentos. Se a IA não estiver configurada (503), o teste é PULADO.

As asserções checam se a resposta CITA as entidades certas vindas do
grafo — não o texto exato (que varia). Isso prova o "grounding": o
modelo respondeu com base nos fatos, não inventando.
"""
import pytest


def _ask_or_skip(client, question):
    r = client.post("/ask", json={"question": question})
    if r.status_code == 503:
        pytest.skip("IA não configurada (chaves/índice ausentes)")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["answer"].strip(), "resposta veio vazia"
    return data


def test_pergunta_projetos_e_validade(client):
    """'Quais projetos usam a licença VMware e quando expira?'"""
    data = _ask_or_skip(
        client, "Quais projetos usam a licença da VMware e quando ela expira?"
    )
    texto = data["answer"].lower()
    assert "datacenter virtualização" in texto or "datacenter virtualizacao" in texto


def test_pergunta_impacto_times(client):
    """'Se a licença vSphere expirar, quais times/centros são impactados?'"""
    data = _ask_or_skip(
        client, "Se a licença vSphere Standard 2026 expirar, quais times e centros de custo são impactados?"
    )
    assert "CC-TI" in data["answer"]


def test_pergunta_gasto_por_centro(client):
    """'Quanto gastamos com a VMware por centro de custo?'"""
    data = _ask_or_skip(
        client, "Quanto gastamos com a VMware por centro de custo?"
    )
    assert "CC-TI" in data["answer"]


def test_resposta_traz_subgrafo(client):
    """A resposta inclui o mini-grafo (context.subgrafo) das entidades usadas."""
    data = _ask_or_skip(
        client, "Quais projetos usam a licença da VMware e quando ela expira?"
    )
    subgrafo = data["context"]["subgrafo"]
    assert subgrafo["nodes"], "esperava um subgrafo com nós"

    ids = {n["id"] for n in subgrafo["nodes"]}
    for e in subgrafo["edges"]:
        assert e["source"] in ids and e["target"] in ids
