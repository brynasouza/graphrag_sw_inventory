"""
Formato (schema) de cada coleção do MongoDB.

Estes modelos Pydantic servem para DOCUMENTAR e VALIDAR a forma dos
documentos. As referências entre coleções são guardadas como o _id
do documento vizinho (aqui representado como texto/str na API).

Grafo de relacionamentos:

    vendors ──< products ──< licenses >── allocations >── projects
       │                        │                            │
       └──< contracts ──────────┘                            │
                                                         teams >── cost_centers
                                          servers ───────────┘
                                          (servers aponta para projects)
"""
from datetime import datetime
from typing import Optional

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
    value: float            # valor total do contrato
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
    unit_cost: float
    currency: str           # ex.: "BRL"
    metric: str             # como é licenciado: "per_cpu", "per_user", "per_host"


class Allocation(BaseModel):
    """
    Ponte muitos-para-muitos entre licença e projeto, COM atributos
    próprios (quantidade e data). É a "aresta" do grafo que permite
    ratear custo e saber quanto cada projeto consome.
    """
    license_id: str         # -> licenses._id
    project_id: str         # -> projects._id
    quantity: int
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
    cpu_sockets: int
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
