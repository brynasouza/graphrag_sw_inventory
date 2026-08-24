"""
Rota do GraphRAG completo (Etapa 6): pergunta -> resposta.

Este é o endpoint principal do produto. Junta as peças:
  busca vetorial (nó de entrada) -> grafo (fatos) -> Claude (redação).

Devolve a resposta em texto E os fatos usados, para dar transparência
(o usuário/front pode conferir de onde veio a resposta).
"""
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
        ctx = context.build_context(body.question, k=body.k)
        resposta = answer.generate_answer(body.question, ctx)
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
