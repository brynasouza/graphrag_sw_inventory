"""
Índices das coleções — para as junções ($lookup / find) não varrerem tudo.

Por que isto existe:
As travessias do grafo "sobem" e "descem" pelas chaves estrangeiras (FKs):
uma alocação aponta para a licença (`license_id`), um servidor aponta para o
projeto (`project_id`), e assim por diante. Sem índice nesses campos, cada
junção é uma VARREDURA da coleção inteira. No tamanho de demo isso custa
pouco, mas é errado — e numa demo enterprise o `explain()` mostrando "COLLSCAN"
tira credibilidade. Com índice, cada junção vira uma busca direta (IXSCAN).

O campo `_id` já é indexado automaticamente pelo MongoDB, então só precisamos
criar índice nos LADOS reversos (os campos que apontam PARA um `_id`).

`create_index` é idempotente: se o índice já existe com a mesma definição, a
chamada é um no-op barato. Por isso é seguro rodar isto a cada startup e no seed.
"""
from typing import List, Tuple

from pymongo.database import Database

from app.models.schemas import Collections as C

# (coleção, campo) — FKs reversos usados nas travessias/agregações e os campos
# filtrados/ordenados nas telas. Inclui license_id / project_id / team_id /
# cost_center_id (junções) e expires_at (filtro+ordenação da tela de alertas).
_INDICES: List[Tuple[str, str]] = [
    (C.ALLOCATIONS, "license_id"),   # travessia licença->alocações; subgrafo
    (C.ALLOCATIONS, "project_id"),   # custo por centro; subgrafo
    (C.PROJECTS, "team_id"),         # projeto->time
    (C.TEAMS, "cost_center_id"),     # time->centro de custo
    (C.SERVERS, "project_id"),       # servidores de um projeto (impacto/subgrafo)
    (C.PRODUCTS, "vendor_id"),       # produtos de um fornecedor
    (C.LICENSES, "product_id"),      # licenças de um produto
    (C.LICENSES, "contract_id"),     # licença->contrato (subgrafo)
    (C.LICENSES, "expires_at"),      # tela de alertas filtra e ordena por expiração
    (C.CONTRACTS, "vendor_id"),      # contratos de um fornecedor
]


def ensure_indexes(db: Database) -> List[str]:
    """
    Cria (se ainda não existirem) os índices das chaves estrangeiras.
    Idempotente: pode ser chamado no startup e no seed sem efeito colateral.
    Devolve a lista de nomes de índice garantidos (útil para log/teste).
    """
    criados: List[str] = []
    for colecao, campo in _INDICES:
        nome = db[colecao].create_index(campo)  # no-op se já existe
        criados.append(f"{colecao}.{nome}")
    return criados
