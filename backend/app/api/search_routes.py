"""
Rota HTTP da busca vetorial (Etapa 5): texto livre -> entidade.

Esta é a porta de entrada do GraphRAG: recebe a pergunta em linguagem
natural e devolve o(s) nó(s) mais prováveis (licença/fornecedor). A
travessia de grafo (Etapas 3 e 4) parte desse nó.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pymongo.errors import OperationFailure
from voyageai.error import VoyageError

from app.retrieval import vector_search

router = APIRouter(prefix="/search", tags=["busca"])


@router.get("")
def buscar(
    q: str = Query(..., min_length=1, description="Pergunta em linguagem natural"),
    k: int = Query(5, ge=1, le=20, description="Quantos resultados devolver"),
    entity_type: Optional[str] = Query(
        None, description="Filtra por tipo: 'license' ou 'vendor'"
    ),
):
    """
    Acha as entidades mais parecidas em SIGNIFICADO com a pergunta.
    Ex.: /search?q=quanto gasto com virtualização
    """
    try:
        return vector_search.search(q, k=k, entity_type=entity_type)
    except (RuntimeError, VoyageError) as exc:
        # Chave da Voyage ausente/inválida -> mensagem clara, não um 500 cru.
        raise HTTPException(
            status_code=503,
            detail=(
                "Busca vetorial indisponível (problema com a Voyage AI). "
                "Confira a VOYAGE_API_KEY no .env. Detalhe: " + str(exc)
            ),
        )
    except OperationFailure as exc:
        # Índice de Vector Search ainda não criado no Atlas.
        raise HTTPException(
            status_code=503,
            detail=(
                "Busca vetorial indisponível. Verifique se o índice "
                "'vector_index' foi criado no Atlas e se o script "
                "build_embeddings já rodou. Detalhe: " + str(exc)
            ),
        )
