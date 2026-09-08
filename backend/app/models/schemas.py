"""
Formato (schema) do MODELO GRAFO-NATIVO no MongoDB.

A demo mostra o MongoDB percorrendo um GRAFO com o operador `$graphLookup`.
Para o `$graphLookup` recursar de verdade, os dados vivem em DUAS coleções
homogêneas (em vez de 9 coleções de domínio com chaves estrangeiras espalhadas):

  - `graph_nodes` — um documento por entidade:
        { _id, tipo, label, props }
    `tipo` é um dos 8 tipos de negócio (vendor…server); `label` é o texto que
    aparece no grafo; `props` guarda os campos de negócio (unit_cost, currency,
    expires_at, metric, code, hostname, cpu_sockets, …).

  - `graph_edges` — um documento por relacionamento, TODOS no mesmo formato:
        { _id, from, to, tipo, props }
    `from`/`to` são _id de nós; `tipo` diz que relação é. Ser homogênea é o que
    permite ao `$graphLookup` seguir `connectFromField:"to"` →
    `connectToField:"from"` recursivamente por vários saltos.

FRONTEIRA ObjectId x string. Dentro do Mongo, `_id`, `from` e `to` são ObjectId
de verdade (é assim que o `$graphLookup` casa os saltos). Na borda HTTP/JSON eles
viram string. As conversões acontecem em UM lugar cada:
  - entrada  (str -> ObjectId): `to_object_id()` em `app/graph/queries.py`
  - saída    (ObjectId -> str): `_clean()` (queries.py), `$toString` nos
             `$project` e `str(_id)` no `GraphBuilder` (`graph/graphdata.py`)

Direção das arestas (sempre no sentido da travessia "para baixo"):

    license → project   (alocacao, props.quantity)
    project → team      (projeto_time)
    team    → cost_center (time_centro)
    license → product   (licenca_produto)
    license → contract  (licenca_contrato)
    product → vendor    (produto_fornecedor)
    contract → vendor   (contrato_fornecedor)
    server  → project   (servidor_projeto)

`allocation` NÃO é um nó: é a aresta `license → project` que carrega a
quantidade em `props.quantity`.
"""
from datetime import datetime
from typing import Any, Dict, Literal

from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    """Um nó do grafo: uma entidade de negócio (fornecedor, licença, projeto…)."""
    tipo: Literal[
        "vendor", "product", "contract", "license",
        "project", "team", "cost_center", "server",
    ]
    label: str                       # texto exibido no grafo
    props: Dict[str, Any] = Field(default_factory=dict)  # campos de negócio


class GraphEdge(BaseModel):
    """Uma aresta do grafo: um relacionamento entre dois nós (from → to)."""
    from_: str = Field(alias="from")  # -> graph_nodes._id (origem)
    to: str                           # -> graph_nodes._id (destino)
    tipo: str                         # ver EdgeTypes
    props: Dict[str, Any] = Field(default_factory=dict)  # ex.: {quantity}

    model_config = {"populate_by_name": True}


# Tipos de aresta (o campo `tipo` de graph_edges), num só lugar para evitar
# erros de digitação nos pipelines de $graphLookup.
class EdgeTypes:
    ALOCACAO = "alocacao"                     # license → project (props.quantity)
    PROJETO_TIME = "projeto_time"             # project → team
    TIME_CENTRO = "time_centro"               # team → cost_center
    LICENCA_PRODUTO = "licenca_produto"       # license → product
    LICENCA_CONTRATO = "licenca_contrato"     # license → contract
    PRODUTO_FORNECEDOR = "produto_fornecedor" # product → vendor
    CONTRATO_FORNECEDOR = "contrato_fornecedor"  # contract → vendor
    SERVIDOR_PROJETO = "servidor_projeto"     # server → project


# Nomes das coleções, num só lugar.
class Collections:
    # Coleções grafo-nativas (o coração do modelo).
    GRAPH_NODES = "graph_nodes"
    GRAPH_EDGES = "graph_edges"
    # Coleção auxiliar da busca vetorial (Etapa 5): guarda o texto de cada
    # entidade pesquisável e seu embedding, para o Atlas Vector Search.
    SEARCH_INDEX = "search_index"
    # Metadados da aplicação. Hoje guarda só o token de versão do seed
    # ({_id:"seed", ran_at}), usado para invalidar o cache do retrieval.
    META = "app_meta"
