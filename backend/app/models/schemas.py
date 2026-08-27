"""
Formato (schema) de cada coleção do MongoDB.

Estes modelos Pydantic servem para DOCUMENTAR e VALIDAR a forma dos
documentos.

FRONTEIRA ObjectId x string. Dentro do Mongo (e dos pipelines de agregação)
o `_id` e as chaves estrangeiras são ObjectId de verdade. Na borda HTTP/JSON
eles viram string. As conversões acontecem em UM lugar cada:
  - entrada  (str -> ObjectId): `to_object_id()` em `app/graph/queries.py`
  - saída    (ObjectId -> str): `_clean()` (queries.py), `$toString` nos
             `$project` e `str(_id)` no `GraphBuilder` (`graph/graphdata.py`)
Por isso os campos de FK abaixo são tipados como `str`: é a forma exposta na
API. NO BANCO eles são ObjectId — nunca insira uma FK como string crua, ou os
`$lookup` (que casam ObjectId com ObjectId) param de encontrar o vizinho.

Grafo de relacionamentos:

    vendors ──< products ──< licenses >── allocations >── projects
       │                        │                            │
       └──< contracts ──────────┘                            │
                                                         teams >── cost_centers
                                          servers ───────────┘
                                          (servers aponta para projects)
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Vendor(BaseModel):
    """Fornecedor de software (ex.: VMware, Microsoft)."""
    name: str


class Product(BaseModel):
    """Produto de um fornecedor (ex.: vSphere, SQL Server)."""
    name: str
    vendor_id: str  # -> vendors._id


class Contract(BaseModel):
    """Contrato guarda-chuva com um fornecedor."""
    vendor_id: str          # -> vendors._id
    reference: str          # número/código do contrato
    value: float = Field(ge=0)   # valor total do contrato (nunca negativo)
    currency: str           # ex.: "BRL"
    starts_at: datetime
    ends_at: datetime


class License(BaseModel):
    """
    Licença de um produto, comprada sob um contrato.
    unit_cost + currency permitem calcular o gasto real
    (unit_cost x quantidade alocada).
    """
    name: str               # rótulo legível (ex.: "vSphere Standard 2026")
    product_id: str         # -> products._id
    contract_id: str        # -> contracts._id
    expires_at: datetime
    unit_cost: float = Field(ge=0)   # custo unitário nunca é negativo
    currency: str           # ex.: "BRL"
    # Como a licença é cobrada. É DESCRITIVO: hoje o custo é sempre
    # unit_cost x quantity, independente da métrica (ver SPEC.md secao 4).
    metric: Literal["per_cpu", "per_host", "per_user"]


class Allocation(BaseModel):
    """
    Ponte muitos-para-muitos entre licença e projeto, COM atributos
    próprios (quantidade e data). É a "aresta" do grafo que permite
    ratear custo e saber quanto cada projeto consome.
    """
    license_id: str         # -> licenses._id
    project_id: str         # -> projects._id
    quantity: int = Field(gt=0)   # alocar 0 (ou menos) unidades não é alocação
    allocated_at: datetime


class Project(BaseModel):
    """Projeto que consome licenças e pertence a um time."""
    name: str
    team_id: str            # -> teams._id


class Team(BaseModel):
    """Time responsável por projetos; ligado a um centro de custo."""
    name: str
    cost_center_id: str     # -> cost_centers._id


class CostCenter(BaseModel):
    """Centro de custo (para onde o gasto é rateado)."""
    name: str
    code: str


class Server(BaseModel):
    """
    Servidor físico/virtual de um projeto. Relevante porque produtos
    como VMware são licenciados por host/CPU (cpu_sockets).
    """
    hostname: str
    cpu_sockets: int = Field(gt=0)   # um servidor tem ao menos 1 soquete
    project_id: str         # -> projects._id


# Nomes das coleções, num só lugar, para evitar erros de digitação.
class Collections:
    VENDORS = "vendors"
    PRODUCTS = "products"
    CONTRACTS = "contracts"
    LICENSES = "licenses"
    ALLOCATIONS = "allocations"
    PROJECTS = "projects"
    TEAMS = "teams"
    COST_CENTERS = "cost_centers"
    SERVERS = "servers"
    # Coleção auxiliar da busca vetorial (Etapa 5): guarda o texto de cada
    # entidade pesquisável e seu embedding, para o Atlas Vector Search.
    SEARCH_INDEX = "search_index"
    # Metadados da aplicação. Hoje guarda só o token de versão do seed
    # ({_id:"seed", ran_at}), usado para invalidar o cache do retrieval.
    META = "app_meta"
