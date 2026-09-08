"""
Verificação de INTEGRIDADE dos dados no MongoDB (modelo grafo-nativo).

Duas classes de problema que corrompem silenciosamente uma demo de custo:

  1. VALORES NEGATIVOS onde não fazem sentido — uma quantidade (na aresta de
     alocação), um custo unitário ou um valor de contrato negativo entra na
     soma e "come" o total de outra linha sem deixar rastro.
  2. ARESTAS ÓRFÃS — uma aresta cujo `from` ou `to` aponta para um _id de nó
     que não existe. O `$graphLookup`/`$lookup` simplesmente não casa aquele
     salto, então o gasto/relacionamento some da conta em vez de dar erro.

`check_integrity(db)` varre as duas coleções e devolve uma lista de mensagens de
violação (vazia = tudo certo). É barata o suficiente para rodar no fim do seed
como rede de segurança e é a base do teste `tests/test_integrity.py`.

Só LÊ o banco — nunca corrige nada sozinha. Corrigir é decisão de quem seeda.
"""
from typing import List

from app.models.schemas import Collections as C
from app.models.schemas import EdgeTypes as E

# (tipo de NÓ, campo em props, mínimo permitido).
# cpu_sockets: > 0 (>= 1). unit_cost/value: >= 0 (zero é aceitável).
_NAO_NEGATIVOS_NOS = [
    ("server", "cpu_sockets", 1),
    ("license", "unit_cost", 0),
    ("contract", "value", 0),
]

# (tipo de ARESTA, campo em props, mínimo permitido).
# quantity da alocação: > 0 (alocar 0 unidades não é alocação).
_NAO_NEGATIVOS_ARESTAS = [
    (E.ALOCACAO, "quantity", 1),
]


def check_integrity(db) -> List[str]:
    """
    Devolve a lista de violações de integridade (vazia = grafo íntegro).

    Cada item é uma mensagem legível dizendo coleção/tipo, _id do documento e o
    que está errado — pronta para log ou para o assert de um teste.
    """
    problemas: List[str] = []
    nodes = db[C.GRAPH_NODES]
    edges = db[C.GRAPH_EDGES]

    # 1a) Valores numéricos negativos em NÓS (unit_cost, value, cpu_sockets).
    for tipo, campo, minimo in _NAO_NEGATIVOS_NOS:
        for doc in nodes.find(
            {"tipo": tipo, f"props.{campo}": {"$lt": minimo}}, {"props": 1}
        ):
            problemas.append(
                f"{C.GRAPH_NODES}[{tipo}]: _id={doc['_id']} tem "
                f"props.{campo}={doc['props'].get(campo)} (esperado >= {minimo})"
            )

    # 1b) Valores numéricos negativos em ARESTAS (quantity da alocação).
    for tipo, campo, minimo in _NAO_NEGATIVOS_ARESTAS:
        for doc in edges.find(
            {"tipo": tipo, f"props.{campo}": {"$lt": minimo}}, {"props": 1}
        ):
            problemas.append(
                f"{C.GRAPH_EDGES}[{tipo}]: _id={doc['_id']} tem "
                f"props.{campo}={doc['props'].get(campo)} (esperado >= {minimo})"
            )

    # 2) Arestas órfãs: cada `from`/`to` precisa apontar para um nó existente.
    node_ids = {d["_id"] for d in nodes.find({}, {"_id": 1})}
    for e in edges.find({}, {"from": 1, "to": 1, "tipo": 1}):
        for ponta in ("from", "to"):
            if e.get(ponta) not in node_ids:
                problemas.append(
                    f"{C.GRAPH_EDGES}[{e.get('tipo')}]: _id={e['_id']} tem "
                    f"{ponta}={e.get(ponta)} inexistente em {C.GRAPH_NODES}"
                )

    return problemas
