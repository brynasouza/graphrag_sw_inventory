"""
Testes de RESILIÊNCIA: como a API se comporta quando algo de fora falha.

Diferente de test_ask.py, aqui NÃO chamamos serviços reais nem o banco — cada
falha é simulada com monkeypatch. O objetivo é provar que toda falha vira uma
mensagem clara (HTTP 503 no /ask; evento SSE 'erro' no /ask/stream) em vez de um
500 cru ou de um corte silencioso no stream (que na tela seriam "tela branca" /
travamento).

Usamos um TestClient próprio (não a fixture `client`, que pula sem Mongo), pois
estes testes não dependem de banco: a falha é injetada antes de qualquer I/O.
"""
import anthropic
import pytest
from fastapi.testclient import TestClient
from pymongo.errors import ServerSelectionTimeoutError
from voyageai.error import RateLimitError

from app.api import ask_routes
from app.main import app
from app.retrieval import vector_search

api = TestClient(app)

# Pergunta FORA da whitelist da demo -> não passa pelo cache (nem toca no banco):
# o fluxo chama direto o vector_search, que monkeypatchamos para falhar.
PERGUNTA_LIVRE = "pergunta qualquer fora da whitelist para forçar o caminho ao vivo"


def _stream_texto(pergunta: str) -> str:
    """Corpo completo (SSE concatenado) do /ask/stream para `pergunta`."""
    r = api.post("/ask/stream", json={"question": pergunta})
    assert r.status_code == 200, r.text  # o stream abre com 200; o erro vem no corpo
    return r.text


# --- 1) Atlas indisponível -------------------------------------------------
def test_atlas_indisponivel_ask_vira_503(monkeypatch):
    """Conexão com o Atlas cai -> /ask responde 503 claro, não 500 cru."""
    def cai(*a, **k):
        raise ServerSelectionTimeoutError("nenhum servidor disponível")

    monkeypatch.setattr(vector_search, "search", cai)
    r = api.post("/ask", json={"question": PERGUNTA_LIVRE})
    assert r.status_code == 503
    assert "Atlas" in r.json()["detail"]


def test_atlas_indisponivel_stream_emite_erro(monkeypatch):
    """No stream, a mesma falha vira um frame 'erro' (nunca corte silencioso)."""
    def cai(*a, **k):
        raise ServerSelectionTimeoutError("nenhum servidor disponível")

    monkeypatch.setattr(vector_search, "search", cai)
    corpo = _stream_texto(PERGUNTA_LIVRE)
    assert "event: erro" in corpo
    assert "Atlas" in corpo


# --- 2) Voyage em rate limit ----------------------------------------------
def test_voyage_rate_limit_ask(monkeypatch):
    """Limite de requisições da Voyage -> 503 com mensagem específica de limite."""
    def cai(*a, **k):
        raise RateLimitError("429 too many requests")

    monkeypatch.setattr(vector_search, "search", cai)
    r = api.post("/ask", json={"question": PERGUNTA_LIVRE})
    assert r.status_code == 503
    assert "limite" in r.json()["detail"].lower()


def test_voyage_rate_limit_stream(monkeypatch):
    def cai(*a, **k):
        raise RateLimitError("429 too many requests")

    monkeypatch.setattr(vector_search, "search", cai)
    corpo = _stream_texto(PERGUNTA_LIVRE)
    assert "event: erro" in corpo
    assert "limite" in corpo.lower()


# --- 3) Anthropic falha NO MEIO do streaming -------------------------------
def test_anthropic_erro_no_meio_do_stream(monkeypatch):
    """
    O Claude escreve alguns tokens e então o serviço cai. O esperado: os tokens
    já enviados aparecem (event: token) E logo depois vem um event: erro
    explicando a parada — parcial preservado, sem travar.
    """
    # Contexto-stub: evita tocar no banco. O fluxo de cache HIT usa só
    # 'candidatos' e 'consultas' antes de chamar o Claude.
    ctx_stub = {"candidatos": [], "consultas": [], "subgrafo": {"nodes": [], "edges": []}}
    monkeypatch.setattr(ask_routes.demo_cache, "obter", lambda p, k: ctx_stub)

    def stream_que_quebra(pergunta, contexto):
        yield "Com base "
        yield "nos fatos"
        raise anthropic.AnthropicError("conexão caiu no meio da geração")

    monkeypatch.setattr(ask_routes.answer, "stream_answer", stream_que_quebra)

    corpo = _stream_texto("qualquer coisa")
    # Ordem: pelo menos um token ANTES do erro.
    assert "event: token" in corpo
    assert "event: erro" in corpo
    assert corpo.index("event: token") < corpo.index("event: erro")
