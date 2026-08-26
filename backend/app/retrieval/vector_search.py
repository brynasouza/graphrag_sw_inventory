"""
Busca vetorial no MongoDB Atlas (Etapa 5).

Recebe um texto livre, transforma em embedding e usa o estágio
`$vectorSearch` do Atlas para achar as entidades mais parecidas em
SIGNIFICADO. É assim que descobrimos o "nó de entrada" do grafo a
partir da pergunta do usuário.

Pré-requisitos (feitos pelo usuário/uma vez):
  1. Preencher VOYAGE_API_KEY no .env.
  2. Rodar o script de indexação:
         .venv/bin/python -m app.ingestion.build_embeddings
  3. Criar no Atlas um índice de Vector Search chamado "vector_index"
     na coleção "search_index" (definição em app/ingestion/atlas_vector_index.json).
"""
import time
from typing import Any, Dict, List, Optional

from app.core.db import get_db
from app.graph import mongosh
from app.models.schemas import Collections as C
from app.retrieval import embeddings

# Nome do índice criado no Atlas (tem que bater exatamente).
INDEX_NAME = "vector_index"


def _pipeline(qvec: List[float], k: int, entity_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Monta o pipeline do $vectorSearch. Separado da execução para que o comando
    exibido em "Ver a consulta" seja o mesmo que roda.
    """
    vector_stage: Dict[str, Any] = {
        "index": INDEX_NAME,
        "path": "embedding",
        "queryVector": qvec,
        # numCandidates: quantos vizinhos o Atlas examina antes de escolher
        # os melhores. Regra prática: bem maior que `k`.
        "numCandidates": max(100, k * 20),
        "limit": k,
    }
    # Filtro opcional por tipo de entidade (usa o campo 'filter' do índice).
    if entity_type:
        vector_stage["filter"] = {"entity_type": {"$eq": entity_type}}

    return [
        {"$vectorSearch": vector_stage},
        {"$project": {
            "_id": 0,
            "entity_type": 1,
            "entity_id": {"$toString": "$entity_id"},
            "name": 1,
            "text": 1,
            "score": {"$meta": "vectorSearchScore"},
        }},
    ]


def search(
    query: str,
    k: int = 5,
    entity_type: Optional[str] = None,
    tempos: Optional[Dict[str, float]] = None,
) -> List[Dict[str, Any]]:
    """
    Devolve as `k` entidades mais parecidas com o texto `query`.
    Se `entity_type` for informado ("license" ou "vendor"), filtra o tipo.

    Cada resultado traz: entity_type, entity_id, name, text e score
    (0 a 1; quanto maior, mais parecido).

    Se `tempos` (dict) for informado, grava nele o tempo em ms de cada
    sub-etapa: 'embedding_query_ms' (chamada à Voyage) e 'vector_search_ms'
    (o $vectorSearch no Atlas). Serve para a instrumentação do /ask — quando
    não é informado, nada muda.
    """
    t0 = time.perf_counter()
    qvec = embeddings.embed_query(query)
    t1 = time.perf_counter()
    resultados = list(get_db()[C.SEARCH_INDEX].aggregate(_pipeline(qvec, k, entity_type)))
    t2 = time.perf_counter()

    if tempos is not None:
        tempos["embedding_query_ms"] = round((t1 - t0) * 1000, 1)
        tempos["vector_search_ms"] = round((t2 - t1) * 1000, 1)

    return resultados


def consulta_vetorial(k: int = 5, entity_type: Optional[str] = None) -> str:
    """
    String mongosh do $vectorSearch (o mesmo pipeline que roda).

    Usa um vetor fictício só para a exibição — o formatador o troca pelo
    marcador "<embedding...>". Assim não gastamos uma chamada à Voyage só
    para mostrar o comando na tela.
    """
    vetor_ficticio = [0.0] * embeddings.DIM
    return mongosh.formatar_aggregate(
        C.SEARCH_INDEX, _pipeline(vetor_ficticio, k, entity_type)
    )
