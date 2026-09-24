"""
Teste do CAMINHO FELIZ do /ask/stream (o contraponto de test_resilience.py).

Como os testes de resiliência, este NÃO toca no banco nem em serviços reais: um
cache HIT é injetado com monkeypatch e a geração do Claude é substituída por um
gerador que emite tokens normalmente. O objetivo é travar o CONTRATO do SSE numa
execução bem-sucedida: a ordem das etapas, o frame de contexto (mini-grafo +
consultas), os tokens e o frame final `fim` — e, crucialmente, NENHUM `erro`.
"""
from fastapi.testclient import TestClient

from app.api import ask_routes
from app.main import app

api = TestClient(app)


def test_stream_feliz_emite_etapas_tokens_e_fim(monkeypatch):
    # Contexto cacheado: o fluxo de cache HIT usa 'candidatos' (para o "resolvido"),
    # 'consultas' e 'subgrafo' — sem nenhum I/O de banco.
    ctx_stub = {
        "candidatos": [{"nome": "vSphere Standard 2026", "tipo": "license", "score": 0.42}],
        "consultas": [{"titulo": "Travessia $graphLookup", "comando": "db.graph.aggregate([...])"}],
        "subgrafo": {"nodes": [{"id": "1", "tipo": "license", "label": "x", "props": {}}], "edges": []},
    }
    monkeypatch.setattr(ask_routes.demo_cache, "obter", lambda p, k: ctx_stub)

    def stream_ok(pergunta, contexto):
        yield "Os projetos "
        yield "são A e B."

    monkeypatch.setattr(ask_routes.answer, "stream_answer", stream_ok)

    r = api.post("/ask/stream", json={"question": "Quais projetos usam a licença vSphere?"})
    assert r.status_code == 200, r.text
    corpo = r.text

    # Sucesso: nenhum frame de erro.
    assert "event: erro" not in corpo

    # Todas as etapas do fluxo aparecem, e na ordem certa.
    for evento in ("event: etapa", "event: contexto", "event: token", "event: fim"):
        assert evento in corpo, f"faltou {evento} no stream"
    assert corpo.index("event: contexto") < corpo.index("event: token") < corpo.index("event: fim")

    # Os tokens do Claude chegaram no corpo (texto parcial preservado).
    assert "Os projetos" in corpo and "são A e B." in corpo
