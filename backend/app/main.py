"""
Ponto de entrada da API (FastAPI).

Rode localmente com:
    cd backend
    uvicorn app.main:app --reload

Depois abra http://localhost:8000/docs para ver a documentação
interativa que o FastAPI gera sozinho.
"""
import threading
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.ask_routes import router as ask_router
from app.api.graph_routes import router as graph_router
from app.api.search_routes import router as search_router
from app.core.config import settings
from app.core.db import get_db, ping
from app.core.indexes import ensure_indexes
from app.retrieval import context, demo_cache

app = FastAPI(
    title="MVP GraphRAG — Inventário de Software",
    description="Responde perguntas sobre licenças, fornecedores e custos.",
    version="0.1.0",
)

# Libera o frontend React (que roda em outra porta) a chamar esta API.
# Em produção, troque "*" pela URL real do frontend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Espaço entre as perguntas do pré-aquecimento. A Voyage (free tier) aceita ~3
# req/min; cada pergunta gera 1 embedding. Com 25s de folga (janela deslizante:
# 3 reqs exigem >=20s entre elas) sobra margem para jitter e para uma pergunta
# do operador durante o aquecimento. Se ainda assim estourar, a pergunta apenas
# não fica pré-aquecida — é servida ao vivo no primeiro /ask (degradação suave).
# Como roda em background, essa lentidão é invisível ao usuário.
_WARMUP_INTERVALO_S = 25.0


def _aquecer_cache():
    """
    Pré-aquece o cache de retrieval das perguntas fixas da demo (embedding +
    vetorial + grafo; NÃO chama o Claude). Assim a primeira pergunta da demo já
    responde rápido, em vez de pagar os ~4s de travessia na estreia.

    Roda em thread de fundo (não atrasa o boot) e engole falhas por pergunta
    (Atlas/Voyage fora não derruba nada). Espaça as chamadas para respeitar o
    limite de req/min da Voyage.
    """
    perguntas = sorted(demo_cache.PERGUNTAS_DEMO)
    for i, pergunta in enumerate(perguntas):
        try:
            context.build_context_cached(pergunta, k=3)
            print(f"[startup] cache aquecido: {pergunta!r}")
        except Exception as exc:  # noqa: BLE001 - aquecimento é best-effort
            print(f"[startup] não aqueci {pergunta!r} agora: {exc}")
        # Não dormir depois da última.
        if i < len(perguntas) - 1:
            time.sleep(_WARMUP_INTERVALO_S)


@app.on_event("startup")
def _garantir_indices():
    """
    Garante os índices das FKs no startup (idempotente). Protegido: se o Atlas
    estiver fora no momento do boot, a app sobe mesmo assim — o erro real
    aparece de forma amigável no /health, não como crash na inicialização.

    Em seguida, dispara o pré-aquecimento do cache EM THREAD DE FUNDO (daemon),
    para não bloquear o boot do uvicorn. Controlado pela flag
    `warmup_cache_on_startup` (desligue em dev para poupar cota da Voyage).
    """
    try:
        ensure_indexes(get_db())
    except Exception as exc:  # noqa: BLE001 - não derruba a app por causa de índice
        print(f"[startup] não foi possível garantir índices agora: {exc}")

    if settings.warmup_cache_on_startup:
        threading.Thread(target=_aquecer_cache, name="warmup-cache", daemon=True).start()


@app.get("/health")
def health():
    """
    Verifica se a API está no ar e se o MongoDB Atlas responde.
    Use isto na Etapa 1 para confirmar que a conexão funciona.
    """
    try:
        ping()
        return {"status": "ok", "mongodb": "conectado"}
    except Exception as exc:  # noqa: BLE001 - queremos mostrar qualquer erro de conexão
        return {"status": "erro", "mongodb": "desconectado", "detalhe": str(exc)}


# Rotas de travessia de grafo (Etapa 3)
app.include_router(graph_router)

# Rota de busca vetorial (Etapa 5)
app.include_router(search_router)

# Rota do GraphRAG completo — pergunta -> resposta (Etapa 6)
app.include_router(ask_router)
