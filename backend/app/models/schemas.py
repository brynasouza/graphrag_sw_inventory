"""
Formato (schema) do MODELO GRAFO-NATIVO no MongoDB.

A demo mostra o MongoDB percorrendo um GRAFO com o operador `$graphLookup`.
Para o `$graphLookup` recursar de verdade — e SEM nenhum `$lookup` para hidratar
rótulos —, os dados vivem numa ÚNICA coleção AUTO-REFERENCIAL (o padrão canônico
do `$graphLookup` na doc do MongoDB):

  - `graph` — um documento por entidade, com suas arestas de SAÍDA embutidas:
        { _id, tipo, label, props, arestas: [ {to, tipo, props}, ... ] }
    `tipo` é um dos 8 tipos de negócio (vendor…server); `label` é o texto que
    aparece no grafo; `props` guarda os campos de negócio (unit_cost, currency,
    expires_at, metric, code, hostname, cpu_sockets, …); `arestas` lista os
    relacionamentos que SAEM deste nó (`to` = _id de outro nó, `tipo` = a relação,
    `props` = atributos da aresta, ex.: `quantity` na alocação).

Por que coleção única e adjacência embutida? Porque assim o `$graphLookup`
recursa DENTRO da própria coleção (`connectFromField:"arestas.to"` →
`connectToField:"_id"`) e cada documento devolvido JÁ TRAZ seu `label`/`props` —
não é preciso um `$lookup` em outra coleção para saber "quem" é o nó alcançado.
Custo fecha localmente: `unit_cost` está no nó da licença e `quantity` na aresta
`alocacao` embutida nele, então `quantity × unit_cost` sai sem join.

FRONTEIRA ObjectId x string. Dentro do Mongo, `_id` e `arestas.to` são ObjectId
de verdade (é assim que o `$graphLookup` casa os saltos). Na borda HTTP/JSON eles
viram string. As conversões acontecem em UM lugar cada:
  - entrada  (str -> ObjectId): `to_object_id()` em `app/graph/queries.py`
  - saída    (ObjectId -> str): `$toString` nos `$project` e `str(_id)` no
             `GraphBuilder` (`graph/graphdata.py`)

Direção das arestas (sempre no sentido da travessia "para baixo"), embutidas no
nó de ORIGEM:

    license → project   (alocacao, props.quantity)
    project → team      (projeto_time)
    team    → cost_center (time_centro)
    license → product   (licenca_produto)
    license → contract  (licenca_contrato)
    product → vendor    (produto_fornecedor)
    contract → vendor   (contrato_fornecedor)
    server  → project   (servidor_projeto)

`allocation` NÃO é um nó: é a aresta `license → project` (embutida na licença)
que carrega a quantidade em `props.quantity`. Uma travessia que precise SUBIR
(ex.: fornecedor ← produto, projeto ← servidor) inverte os campos do
`$graphLookup`: `connectFromField:"_id"` → `connectToField:"arestas.to"`.
"""
from datetime import datetime
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field


class Aresta(BaseModel):
    """Uma aresta de SAÍDA embutida num nó (origem → to)."""
    to: str                           # -> graph._id (destino)
    tipo: str                         # ver EdgeTypes
    props: Dict[str, Any] = Field(default_factory=dict)  # ex.: {quantity}


class GraphNode(BaseModel):
    """Um nó do grafo: uma entidade de negócio, com suas arestas de saída."""
    tipo: Literal[
        "vendor", "product", "contract", "license",
        "project", "team", "cost_center", "server",
    ]
    label: str                       # texto exibido no grafo
    props: Dict[str, Any] = Field(default_factory=dict)  # campos de negócio
    arestas: List[Aresta] = Field(default_factory=list)  # relacionamentos de saída


# Tipos de aresta (o campo `tipo` de cada aresta embutida em `graph`), num só
# lugar para evitar erros de digitação nos pipelines de $graphLookup.
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
    # Coleção grafo-nativa auto-referencial (o coração do modelo): nós com suas
    # arestas de saída embutidas. O `$graphLookup` recursa DENTRO dela.
    GRAPH = "graph"
    # Coleção auxiliar da busca vetorial (Etapa 5): guarda o texto de cada
    # entidade pesquisável e seu embedding, para o Atlas Vector Search.
    SEARCH_INDEX = "search_index"
    # Metadados da aplicação. Hoje guarda só o token de versão do seed
    # ({_id:"seed", ran_at}), usado para invalidar o cache do retrieval.
    META = "app_meta"
