"""
Verificação de INTEGRIDADE dos dados no MongoDB.

Duas classes de problema que corrompem silenciosamente uma demo de custo:

  1. VALORES NEGATIVOS onde não fazem sentido — uma quantidade, um custo
     unitário ou um valor de contrato negativo entra na soma e "come" o total
     de outra linha sem deixar rastro.
  2. REFERÊNCIAS ÓRFÃS — uma chave estrangeira (license_id, project_id, ...)
     apontando para um _id que não existe mais. O `$lookup` some com a linha
     (`$unwind` de array vazio), então o gasto simplesmente desaparece da
     conta em vez de dar erro.

`check_integrity(db)` varre as coleções e devolve uma lista de mensagens de
violação (vazia = tudo certo). É barata o suficiente para rodar no fim do seed
como rede de segurança e é a base do teste `tests/test_integrity.py`.

Só LÊ o banco — nunca corrige nada sozinha. Corrigir é decisão de quem seeda.
"""
from typing import Any, Dict, List

from app.models.schemas import Collections as C

# (coleção, campo FK, coleção-alvo) — mesma topologia dos índices reversos em
# core/indexes.py. Cada FK precisa resolver para um _id existente no alvo.
_REFERENCIAS = [
    (C.PRODUCTS, "vendor_id", C.VENDORS),
    (C.CONTRACTS, "vendor_id", C.VENDORS),
    (C.LICENSES, "product_id", C.PRODUCTS),
    (C.LICENSES, "contract_id", C.CONTRACTS),
    (C.ALLOCATIONS, "license_id", C.LICENSES),
    (C.ALLOCATIONS, "project_id", C.PROJECTS),
    (C.PROJECTS, "team_id", C.TEAMS),
    (C.TEAMS, "cost_center_id", C.COST_CENTERS),
    (C.SERVERS, "project_id", C.PROJECTS),
]

# (coleção, campo numérico, mínimo permitido) — abaixo disso é violação.
# quantity/cpu_sockets: > 0 (>= 1). unit_cost/value: >= 0 (zero é aceitável).
_NAO_NEGATIVOS = [
    (C.ALLOCATIONS, "quantity", 1),
    (C.SERVERS, "cpu_sockets", 1),
    (C.LICENSES, "unit_cost", 0),
    (C.CONTRACTS, "value", 0),
]


def _ids_existentes(db, colecao: str) -> set:
    """Conjunto dos _id de uma coleção (para checar referências rapidamente)."""
    return {d["_id"] for d in db[colecao].find({}, {"_id": 1})}


def check_integrity(db) -> List[str]:
    """
    Devolve a lista de violações de integridade (vazia = banco íntegro).

    Cada item é uma mensagem legível dizendo coleção, _id do documento e o que
    está errado — pronta para log ou para o assert de um teste.
    """
    problemas: List[str] = []

    # 1) Valores numéricos negativos (ou zero onde exige-se positivo).
    for colecao, campo, minimo in _NAO_NEGATIVOS:
        for doc in db[colecao].find({campo: {"$lt": minimo}}, {campo: 1}):
            problemas.append(
                f"{colecao}: _id={doc['_id']} tem {campo}={doc[campo]} "
                f"(esperado >= {minimo})"
            )

    # 2) Referências órfãs: cada FK precisa apontar para um _id que existe.
    cache_ids: Dict[str, set] = {}
    for colecao, campo, alvo in _REFERENCIAS:
        if alvo not in cache_ids:
            cache_ids[alvo] = _ids_existentes(db, alvo)
        validos = cache_ids[alvo]
        for doc in db[colecao].find({}, {campo: 1}):
            ref = doc.get(campo)
            if ref not in validos:
                problemas.append(
                    f"{colecao}: _id={doc['_id']} referencia {campo}={ref} "
                    f"inexistente em {alvo}"
                )

    return problemas
