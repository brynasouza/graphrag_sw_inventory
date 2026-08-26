"""
Rota do GraphRAG completo (Etapa 6): pergunta -> resposta.

Este é o endpoint principal do produto. Junta as peças:
  busca vetorial (nó de entrada) -> grafo (fatos) -> Claude (redação).

Devolve a resposta em texto E os fatos usados, para dar transparência
(o usuário/front pode conferir de onde veio a resposta).
"""
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from pymongo.errors import OperationFailure
from voyageai.error import VoyageError
import anthropic

from app.llm import answer
from app.retrieval import context

router = APIRouter(prefix="/ask", tags=["graphrag"])


class Pergunta(BaseModel):
    question: str = Field(..., min_length=1, description="Pergunta em linguagem natural")
    k: int = Field(3, ge=1, le=10, description="Quantos candidatos considerar")


@router.post("")
def perguntar(body: Pergunta):
    """
    Responde uma pergunta de negócio combinando grafo + IA.
    Ex.: {"question": "Quanto gastamos com a VMware por centro de custo?"}
    """
    try:
        t_inicio = time.perf_counter()

        # build_context já mede embedding_query_ms, vector_search_ms e
        # grafo_lookup_agg_ms dentro de ctx["tempos"].
        ctx = context.build_context(body.question, k=body.k)

        t_claude = time.perf_counter()
        resposta = answer.generate_answer(body.question, ctx)

        tempos = ctx.setdefault("tempos", {})
        tempos["geracao_claude_ms"] = round((time.perf_counter() - t_claude) * 1000, 1)
        tempos["total_ms"] = round((time.perf_counter() - t_inicio) * 1000, 1)

        # Log no stdout do uvicorn: onde o tempo foi gasto, por etapa.
        print(
            "[/ask] tempos(ms): "
            f"embedding={tempos.get('embedding_query_ms')} "
            f"vector_search={tempos.get('vector_search_ms')} "
            f"grafo={tempos.get('grafo_lookup_agg_ms')} "
            f"claude={tempos.get('geracao_claude_ms')} "
            f"total={tempos.get('total_ms')} "
            f"| pergunta={body.question[:60]!r}"
        )

        return {"answer": resposta, "context": ctx}
    except (RuntimeError, VoyageError, anthropic.AnthropicError) as exc:
        # Chave/serviço de IA indisponível -> mensagem clara.
        raise HTTPException(
            status_code=503,
            detail="Serviço de IA indisponível. Confira as chaves no .env. "
                   "Detalhe: " + str(exc),
        )
    except OperationFailure as exc:
        # Índice de Vector Search ausente no Atlas.
        raise HTTPException(
            status_code=503,
            detail="Busca vetorial indisponível (índice 'vector_index' no "
                   "Atlas?). Detalhe: " + str(exc),
        )
