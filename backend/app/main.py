"""
Ponto de entrada da API (FastAPI).

Rode localmente com:
    cd backend
    uvicorn app.main:app --reload

Depois abra http://localhost:8000/docs para ver a documentação
interativa que o FastAPI gera sozinho.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.ask_routes import router as ask_router
from app.api.graph_routes import router as graph_router
from app.api.search_routes import router as search_router
from app.core.db import ping

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
