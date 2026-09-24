"""
Verificação de INTEGRIDADE dos dados no MongoDB (grafo auto-referencial).

Duas classes de problema que corrompem silenciosamente uma demo de custo:

  1. VALORES NEGATIVOS onde não fazem sentido — uma quantidade (na aresta de
     alocação embutida), um custo unitário ou um valor de contrato negativo
     entra na soma e "come" o total de outra linha sem deixar rastro.
  2. ARESTAS ÓRFÃS — uma aresta embutida cujo `to` aponta para um _id de nó que
     não existe. O `$graphLookup` simplesmente não casa aquele salto, então o
     gasto/relacionamento some da conta em vez de dar erro.

`check_integrity(db)` varre a coleção `graph` (nós + suas arestas embutidas) e
devolve uma lista de mensagens de violação (vazia = tudo certo). É barata o
suficiente para rodar no fim do seed como rede de segurança e é a base do teste
`tests/test_integrity.py`.

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
    graph = db[C.GRAPH]

    # 1a) Valores numéricos negativos em NÓS (unit_cost, value, cpu_sockets).
    for tipo, campo, minimo in _NAO_NEGATIVOS_NOS:
        for doc in graph.find(
            {"tipo": tipo, f"props.{campo}": {"$lt": minimo}}, {"props": 1}
        ):
            problemas.append(
                f"{C.GRAPH}[{tipo}]: _id={doc['_id']} tem "
                f"props.{campo}={doc['props'].get(campo)} (esperado >= {minimo})"
            )

    # 1b) Valores numéricos negativos em ARESTAS embutidas (quantity da alocação).
    for tipo, campo, minimo in _NAO_NEGATIVOS_ARESTAS:
        for doc in graph.find(
            {"arestas": {"$elemMatch": {"tipo": tipo, f"props.{campo}": {"$lt": minimo}}}},
            {"arestas": 1},
        ):
            for a in doc.get("arestas", []):
                if a.get("tipo") == tipo and a.get("props", {}).get(campo, minimo) < minimo:
                    problemas.append(
                        f"{C.GRAPH}[{tipo}]: _id={doc['_id']} tem uma aresta com "
                        f"props.{campo}={a['props'].get(campo)} (esperado >= {minimo})"
                    )

    # 2) Arestas órfãs: cada `arestas.to` precisa apontar para um nó existente.
    node_ids = {d["_id"] for d in graph.find({}, {"_id": 1})}
    for doc in graph.find({}, {"arestas": 1}):
        for a in doc.get("arestas", []):
            if a.get("to") not in node_ids:
                problemas.append(
                    f"{C.GRAPH}[{a.get('tipo')}]: _id={doc['_id']} tem uma aresta com "
                    f"to={a.get('to')} inexistente em {C.GRAPH}"
                )

    return problemas
