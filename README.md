# MVP GraphRAG — Inventário de Software Corporativo

Um MVP que responde **perguntas de negócio em linguagem natural** sobre o
inventário de software de uma empresa (licenças, fornecedores, contratos,
projetos e custos), combinando um **grafo de relacionamentos no MongoDB**
com um **LLM (Claude)**. É a técnica **GraphRAG**: o grafo garante os
_fatos_; o LLM garante a _linguagem_.

## Perguntas que ele responde

- _"Quais projetos usam a licença da VMware e quando ela expira?"_
- _"Se a licença X expirar, quais times/centros de custo são impactados?"_
- _"Quanto gastamos com o fornecedor Y por centro de custo?"_

## Como funciona (arquitetura)

```
Pergunta do usuário
      │
      ▼
1) Busca vetorial (Atlas Vector Search + Voyage AI)
      │  acha o "nó de entrada" (a licença/fornecedor que o usuário quis dizer)
      ▼
2) Travessia do grafo ($lookup encadeado no MongoDB)
      │  licença → allocations → projeto → time → centro de custo → servidores
      ▼
3) Agregações de custo (unit_cost × quantity)
      │  soma o gasto por fornecedor / centro de custo
      ▼
4) Geração da resposta (Claude claude-opus-5)
      │  redige em português usando SOMENTE os fatos coletados
      ▼
Resposta + fatos usados (transparência)
```

> **Por que `$lookup` encadeado e não `$graphLookup`?**
> O caminho `licença → projeto → time → centro de custo` atravessa
> **coleções diferentes** com profundidade fixa, então usamos um `$lookup`
> por salto. `$graphLookup` só serve para hierarquias auto-referenciadas
> (uma coleção que aponta para ela mesma), o que não existe neste modelo.

## Stack

| Camada | Tecnologia |
|---|---|
| Backend | Python, FastAPI, pymongo |
| Banco | MongoDB Atlas (+ Atlas Vector Search) |
| Embeddings | Voyage AI (`voyage-3.5`) |
| LLM | Anthropic Claude (`claude-opus-5`) |
| Frontend | React + Vite + TypeScript |

## Modelo de dados (9 coleções)

Ligadas por **referências** (`_id` do vizinho), para navegar o grafo em
qualquer direção.

| Coleção | Campos-chave | Papel |
|---|---|---|
| `vendors` | `name` | Fornecedores (VMware, Microsoft, Oracle, Red Hat, Atlassian) |
| `products` | `vendor_id`, `name` | Produtos de cada fornecedor |
| `contracts` | `vendor_id`, `value`, `currency` | Contratos guarda-chuva |
| `licenses` | `product_id`, `contract_id`, `expires_at`, `unit_cost`, `currency`, `metric` | Licenças, com custo unitário |
| `allocations` | `license_id`, `project_id`, `quantity`, `allocated_at` | **Ponte licença↔projeto** (aresta do grafo); permite ratear custo |
| `projects` | `team_id`, `name` | Projetos |
| `teams` | `cost_center_id`, `name` | Times |
| `cost_centers` | `code`, `name` | Centros de custo |
| `servers` | `hostname`, `cpu_sockets`, `project_id` | Servidores (VMware é licenciado por host/CPU) |

> **Custo real** = `licenses.unit_cost` × `allocations.quantity`, somado
> por fornecedor ou centro de custo.

A coleção auxiliar `search_index` guarda o texto + embedding de cada
entidade pesquisável (criada pelo script de embeddings).

## Estrutura de pastas

```
MVP_GraphRAG/
├── backend/
│   ├── app/
│   │   ├── api/         # endpoints HTTP (/graph, /search, /ask)
│   │   ├── core/        # config (.env) e conexão MongoDB
│   │   ├── models/      # schemas Pydantic + nomes das coleções
│   │   ├── graph/       # travessia ($lookup) e agregações de custo
│   │   ├── retrieval/   # embeddings, busca vetorial e montagem de contexto
│   │   ├── llm/         # geração da resposta com o Claude
│   │   └── ingestion/   # seed + build de embeddings + def. do índice Atlas
│   └── tests/           # testes de integração (pytest)
├── frontend/
│   └── src/
│       ├── theme/       # theme.ts → UM arquivo: logo + paleta (re-tematização)
│       ├── components/  # UI
│       └── pages/       # telas
├── .env.example         # modelo das variáveis (SEM segredos)
├── .gitignore
└── README.md
```

## Pré-requisitos

- Python 3.9+
- Node.js 18+
- Uma conta no **MongoDB Atlas** (cluster criado)
- Chaves de API: **Anthropic** e **Voyage AI**

## Como rodar

### 1. Variáveis de ambiente

```bash
cp .env.example .env
```
Edite o `.env` e preencha `MONGODB_URI`, `ANTHROPIC_API_KEY` e
`VOYAGE_API_KEY` com valores reais. **O `.env` está no `.gitignore` e
nunca deve ser versionado.**

### 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Carrega os dados de exemplo (idempotente)
python -m app.ingestion.seed
```

### 3. Índice de busca vetorial (uma vez)

```bash
# Gera os embeddings das entidades na coleção search_index
python -m app.ingestion.build_embeddings
```
Depois, no site do Atlas, crie um índice **Atlas Vector Search** chamado
`vector_index` na coleção `search_index`, usando a definição em
[`backend/app/ingestion/atlas_vector_index.json`](backend/app/ingestion/atlas_vector_index.json).

### 4. Subir a API

```bash
uvicorn app.main:app --reload
# API em http://localhost:8000  •  docs em http://localhost:8000/docs
```

### 5. Frontend

```bash
cd frontend
npm install
npm run dev
# Abre em http://localhost:5173
```

## Endpoints principais

| Método | Rota | Descrição |
|---|---|---|
| GET | `/health` | Verifica API + conexão com o Atlas |
| GET | `/graph/licenses?expiring_in_days=90` | Licenças (opcionalmente as que vencem em N dias) |
| GET | `/graph/licenses/{id}/impact` | Impacto se a licença expirar |
| GET | `/graph/costs/by-cost-center?vendor=VMware` | Gasto por centro de custo |
| GET | `/graph/costs/by-vendor` | Gasto por fornecedor |
| GET | `/search?q=...` | Busca vetorial (texto → entidade) |
| POST | `/ask` | **GraphRAG completo** (pergunta → resposta) |

Exemplo:
```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Quanto gastamos com a VMware por centro de custo?"}'
```

## Testes

```bash
cd backend
python -m pytest -q
```
São testes de **integração** (usam o Atlas real). Se o banco/IA estiverem
inacessíveis, os testes correspondentes são **pulados** em vez de falhar.

## Re-tematização (white-label)

Para adaptar o app a outra marca, edite **apenas um arquivo**:
[`frontend/src/theme/theme.ts`](frontend/src/theme/theme.ts) — troque o
nome, o `logo` e a paleta de `colors`. As cores viram variáveis CSS
aplicadas em todo o app; nada mais precisa mudar.

## Segurança

- O `.env` (com a connection string do Atlas e as chaves de IA) **nunca**
  é versionado — está no `.gitignore`.
- Apenas o `.env.example` (sem valores reais) vai para o repositório.
- O `.gitignore` também exclui chaves/certificados (`*.pem`, `*.key`,
  `credentials*`, `secrets*`, etc.), `node_modules/`, `.venv/` e temporários.
