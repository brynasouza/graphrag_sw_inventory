"""
Geração de embeddings com a Voyage AI (Etapa 5).

O que é um embedding? É uma lista de números que representa o SIGNIFICADO
de um texto. Textos parecidos viram listas de números parecidas. É isso
que permite achar a licença certa mesmo quando o usuário usa outras
palavras (ex.: "virtualização" -> "vSphere / VMware").

Usamos a Voyage AI porque é o provedor de embeddings recomendado pela
Anthropic. A chave (VOYAGE_API_KEY) fica no .env; o cliente é criado de
forma preguiçosa (só no primeiro uso), então importar este módulo nunca
quebra por falta de chave.
"""
from typing import List, Optional

import voyageai

from app.core.config import settings

# Modelo de embeddings e nº de dimensões do vetor.
# ATENÇÃO: este número (1024) TEM que ser o mesmo configurado no índice
# do Atlas Vector Search, senão a busca falha.
MODEL = "voyage-3.5"
DIM = 1024

_client: Optional[voyageai.Client] = None


def _get_client() -> voyageai.Client:
    """Cria (uma vez) o cliente Voyage. Erro amigável se faltar a chave."""
    global _client
    if _client is None:
        if not settings.voyage_api_key:
            raise RuntimeError(
                "VOYAGE_API_KEY não configurada no .env. "
                "Preencha a chave da Voyage AI para usar a busca vetorial."
            )
        _client = voyageai.Client(api_key=settings.voyage_api_key)
    return _client


def embed_documents(texts: List[str]) -> List[List[float]]:
    """
    Gera embeddings para textos que serão GUARDADOS no banco (input_type
    'document'). Use ao construir o índice.
    """
    result = _get_client().embed(
        texts, model=MODEL, input_type="document", output_dimension=DIM
    )
    return result.embeddings


def embed_query(text: str) -> List[float]:
    """
    Gera o embedding de uma PERGUNTA do usuário (input_type 'query').
    A Voyage otimiza o vetor de forma diferente para pergunta x documento,
    por isso distinguimos os dois casos.
    """
    result = _get_client().embed(
        [text], model=MODEL, input_type="query", output_dimension=DIM
    )
    return result.embeddings[0]
