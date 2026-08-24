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
from typing import Any, Dict, List, Optional

from app.core.db import get_db
from app.models.schemas import Collections as C
from app.retrieval import embeddings

# Nome do índice criado no Atlas (tem que bater exatamente).
INDEX_NAME = "vector_index"


def search(query: str, k: int = 5, entity_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Devolve as `k` entidades mais parecidas com o texto `query`.
    Se `entity_type` for informado ("license" ou "vendor"), filtra o tipo.

    Cada resultado traz: entity_type, entity_id, name, text e score
    (0 a 1; quanto maior, mais parecido).
    """
    qvec = embeddings.embed_query(query)

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

    pipeline = [
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
    return list(get_db()[C.SEARCH_INDEX].aggregate(pipeline))
