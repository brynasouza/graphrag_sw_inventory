"""
Testes dos endpoints de visualização de grafo.

/graph/explore não usa IA — só o MongoDB. Se o banco estiver inacessível
(503 ou fixture pulada), o teste é pulado, seguindo o padrão do projeto.

Checamos a INTEGRIDADE do grafo: toda aresta aponta para nós existentes.
"""
import pytest


def test_explore_retorna_grafo_integro(client):
    """O grafo inteiro tem nós e arestas coerentes (arestas ligam nós reais)."""
    r = client.get("/graph/explore")
    if r.status_code == 503:
        pytest.skip("Banco indisponível para montar o grafo")
    assert r.status_code == 200, r.text

    data = r.json()
    assert data["nodes"], "esperava ao menos um nó no grafo"
    assert data["edges"], "esperava ao menos uma aresta no grafo"

    ids = {n["id"] for n in data["nodes"]}
    for e in data["edges"]:
        assert e["source"] in ids, f"aresta aponta para nó inexistente: {e}"
        assert e["target"] in ids, f"aresta aponta para nó inexistente: {e}"

    # Os tipos principais do modelo devem aparecer.
    tipos = {n["tipo"] for n in data["nodes"]}
    assert {"vendor", "license", "project", "cost_center"} <= tipos


def test_explore_respeita_limite(client):
    """
    ?limite=N corta cada coleção em N documentos e sinaliza `truncado`.
    Com o default (200 >> demo), nada é cortado (`truncado` False).
    """
    r = client.get("/graph/explore", params={"limite": 1})
    if r.status_code == 503:
        pytest.skip("Banco indisponível para montar o grafo")
    data = r.json()
    # 8 tipos de nó (allocations viram aresta), no máximo 1 doc por coleção.
    assert len(data["nodes"]) <= 8
    assert data["truncado"] is True

    # Default: demo pequena cabe folgada -> nada truncado.
    padrao = client.get("/graph/explore").json()
    assert padrao["truncado"] is False


def test_subgrafo_de_licenca(client):
    """O subgrafo de uma licença inclui a própria licença e é íntegro."""
    lics = client.get("/graph/licenses").json()
    if not lics:
        pytest.skip("sem licenças no banco")
    license_id = lics[0]["_id"]

    r = client.get(f"/graph/licenses/{license_id}/subgraph")
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["nodes"], "esperava nós no subgrafo"
    assert any(n["tipo"] == "license" for n in data["nodes"]), \
        "a licença de entrada deveria estar no subgrafo"

    ids = {n["id"] for n in data["nodes"]}
    for e in data["edges"]:
        assert e["source"] in ids and e["target"] in ids
