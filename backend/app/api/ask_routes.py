"""
Rota do GraphRAG completo (Etapa 6): pergunta -> resposta.

Este é o endpoint principal do produto. Junta as peças:
  busca vetorial (nó de entrada) -> grafo (fatos) -> Claude (redação).

Devolve a resposta em texto E os fatos usados, para dar transparência
(o usuário/front pode conferir de onde veio a resposta).
"""
import json
import time
from typing import Any, Dict, Iterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from pymongo.errors import OperationFailure
from voyageai.error import VoyageError
import anthropic

from app.llm import answer
from app.retrieval import context, vector_search

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


# ---------------------------------------------------------------------------
# Versão em STREAMING (SSE) — mesma resposta, mas em tempo real.
#
# Por que existe em paralelo ao /ask:
#   - o /ask (acima) continua igual -> os testes-alvo não mudam;
#   - o /ask/stream manda eventos conforme cada etapa acontece, então a tela
#     mostra o progresso ("buscando -> percorrendo -> redigindo") e o texto do
#     Claude palavra a palavra. Numa demo, ver o sistema trabalhando vende a
#     narrativa das duas fases do GraphRAG (busca semântica + travessia).
#
# Formato: Server-Sent Events (SSE). Cada evento é "event: <nome>\n data:
# <json>\n\n". A função geradora é SÍNCRONA de propósito: o FastAPI a roda num
# threadpool, então o pymongo síncrono e o streaming síncrono do Anthropic
# funcionam sem bloquear o event loop.
# ---------------------------------------------------------------------------
def _sse(evento: str, dados: Any) -> str:
    """Formata um frame SSE (default=str serializa datas/ObjectId)."""
    return f"event: {evento}\ndata: {json.dumps(dados, ensure_ascii=False, default=str)}\n\n"


def _fluxo_resposta(pergunta: str, k: int) -> Iterator[str]:
    t_inicio = time.perf_counter()
    tempos: Dict[str, float] = {}
    try:
        # Etapa 1: busca vetorial (acha o nó de entrada).
        yield _sse("etapa", {"etapa": "buscando", "label": "Buscando a entidade"})
        hits = vector_search.search(pergunta, k=k, tempos=tempos)
        resolvido = ", ".join(
            f"{h['name']} ({h['entity_type']}, score {h['score']:.3f})" for h in hits
        )

        # Etapa 2: travessia do grafo (reúne os fatos).
        yield _sse("etapa", {
            "etapa": "percorrendo",
            "label": "Percorrendo o grafo",
            "resolvido": resolvido,
        })
        ctx = context.build_from_hits(pergunta, hits, k, tempos)

        # Manda o contexto JÁ — a tela desenha o mini-grafo e o painel
        # "Ver a consulta" enquanto o Claude ainda está redigindo.
        yield _sse("contexto", ctx)

        # Etapa 3: redação da resposta (Claude), palavra a palavra.
        yield _sse("etapa", {"etapa": "redigindo", "label": "Redigindo a resposta"})
        t_claude = time.perf_counter()
        for pedaco in answer.stream_answer(pergunta, ctx):
            yield _sse("token", {"t": pedaco})
        tempos["geracao_claude_ms"] = round((time.perf_counter() - t_claude) * 1000, 1)
        tempos["total_ms"] = round((time.perf_counter() - t_inicio) * 1000, 1)

        print(
            "[/ask/stream] tempos(ms): "
            f"embedding={tempos.get('embedding_query_ms')} "
            f"vector_search={tempos.get('vector_search_ms')} "
            f"grafo={tempos.get('grafo_lookup_agg_ms')} "
            f"claude={tempos.get('geracao_claude_ms')} "
            f"total={tempos.get('total_ms')} "
            f"| pergunta={pergunta[:60]!r}"
        )

        yield _sse("fim", {"tempos": tempos})
    except (RuntimeError, VoyageError, anthropic.AnthropicError) as exc:
        yield _sse("erro", {"detail": "Serviço de IA indisponível. Confira as "
                                      "chaves no .env. Detalhe: " + str(exc)})
    except OperationFailure as exc:
        yield _sse("erro", {"detail": "Busca vetorial indisponível (índice "
                                      "'vector_index' no Atlas?). Detalhe: " + str(exc)})


@router.post("/stream")
def perguntar_stream(body: Pergunta):
    """
    Igual ao /ask, mas responde em STREAMING (SSE): emite as etapas conforme
    acontecem e o texto do Claude palavra a palavra. Consumir com um cliente
    que leia text/event-stream (o frontend usa fetch + ReadableStream).
    """
    return StreamingResponse(
        _fluxo_resposta(body.question, body.k),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
