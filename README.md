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
> por fornecedor ou centro de custo. A soma é **agrupada por moeda**: cada
> par (grupo, moeda) vira uma linha própria, então gastos em moedas diferentes
> nunca colapsam num único total sem conversão.

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

# Carrega os dados de exemplo (determinístico e idempotente)
python -m app.ingestion.seed
```

> O seed é **determinístico**: os `_id` de cada documento são derivados de
> uma chave natural (nome/código), então rodá-lo de novo produz exatamente os
> mesmos identificadores. As datas de expiração são **relativas** à data de
> hoje (para "vencer em 90 dias" seguir verdadeiro) — fixe-as com a variável
> `SEED_DATA_BASE=2026-01-01` se precisar de datas estáveis (ex.: em teste).

> **Validação de integridade.** Ao final, o seed roda `check_integrity`, que
> varre valores negativos (quantidade, custo, sockets) e **referências órfãs**
> (uma FK que aponta para um `_id` inexistente) — imprime um aviso se achar
> algo, sem derrubar o seed. Na entrada, os schemas Pydantic já barram o
> inválido: `quantity`/`cpu_sockets > 0`, `unit_cost`/`value ≥ 0` e `metric`
> restrita a `per_cpu | per_host | per_user`.

### 3. Índice de busca vetorial (uma vez)

```bash
# Gera os embeddings das entidades na coleção search_index
python -m app.ingestion.build_embeddings
```
Depois, no site do Atlas, crie um índice **Atlas Vector Search** chamado
`vector_index` na coleção `search_index`, usando a definição em
[`backend/app/ingestion/atlas_vector_index.json`](backend/app/ingestion/atlas_vector_index.json).

> **Seed × search_index.** O `seed.py` **não** apaga a coleção `search_index`
> — quem a (re)constrói é o `build_embeddings.py`. Como os `_id` do seed são
> estáveis, re-seedar mantém os `entity_id` válidos: só é preciso rodar o
> `build_embeddings` de novo quando as **entidades ou seus textos mudarem**,
> não a cada seed.

> **Embeddings incrementais.** O `build_embeddings.py` é **incremental e
> econômico**: compara o texto de cada entidade com o já indexado, só chama a
> Voyage para o que é **novo ou mudou**, reaproveita os vetores inalterados e
> remove órfãos. Uma 2ª rodada sem nenhuma mudança **não gasta cota** da Voyage.
> Uma chave única `(entity_type, entity_id)` na `search_index` sustenta o upsert
> e impede duplicatas (criada pelo próprio script, não precisa fazer no Atlas).

> **Âncora semântica.** O texto vetorizado inclui uma descrição funcional em
> alguns produtos (OpenShift → contêineres/Kubernetes; Confluence/Jira →
> colaboração e documentação) para que perguntas por _conceito_ ("o que temos
> de plataforma de contêineres?") encontrem a entidade certa. Esse conceito
> vive só no texto indexado, **não** nos campos de negócio — um `find()` por
> palavra-chave não acharia. É o que a busca vetorial demonstra.

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
| POST | `/ask/stream` | Igual ao `/ask`, mas em **streaming (SSE)**: emite as etapas e o texto do Claude em tempo real |

> O `/ask/stream` responde em **Server-Sent Events**: eventos `etapa`
> (progresso: buscando → percorrendo → redigindo), `contexto` (os fatos e os
> comandos MongoDB, que chegam antes do texto), `token` (a resposta palavra a
> palavra) e `fim`. É o que a tela "Perguntar" consome para mostrar o sistema
> trabalhando. (O evento `erro` de encerramento está descrito em _Resiliência_.)

> Os GETs de grafo/custo aceitam `?incluir_consulta=true`: a resposta passa a
> ser `{ dados, consulta }`, onde `consulta` é o comando MongoDB real por trás
> do resultado (pronto para colar no `mongosh`). É o que alimenta o painel
> "Ver a consulta" no frontend. O `/ask` já traz esses comandos em
> `context.consultas`. Sem o parâmetro, a resposta é idêntica à de sempre.

> **Desempenho.** As junções `$lookup` de custo/travessia trazem só os campos
> usados (sub-pipeline `$project`) e casam pela chave indexada. Há índice em
> `licenses.expires_at` (a tela de alertas filtra e ordena por ele). O
> `/graph/explore` lê no máximo `?limite=N` documentos por coleção (default
> 200) e marca `truncado=true` se cortou — protege contra um inventário grande
> sem alterar a demo (~60 nós).

Exemplo:
```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Quanto gastamos com a VMware por centro de custo?"}'
```

## Cache das perguntas da demo

As perguntas fixas usadas na demonstração se repetem. Para deixá-las quase
instantâneas — e independentes do limite de requisições da Voyage — o
_retrieval_ inteiro (busca vetorial + travessia do grafo) dessas perguntas é
guardado em um cache em memória (whitelist: só elas entram). Em um acerto, sobra
apenas a geração do Claude; os comandos MongoDB das **duas fases** continuam no
painel "Ver a consulta", idênticos a uma execução normal.

> **Invalidação por token do seed.** Ao rodar, o `seed.py` grava um token de
> versão em `app_meta` (`{_id: "seed", ran_at}`). Cada consulta confere esse
> token com um `find_one` por `_id` (a operação mais barata do Atlas), no máximo
> uma vez a cada poucos segundos. Se o token mudou (o seed rodou de novo), o
> cache é descartado — os dados podem ter mudado.

## Resiliência

Falhas externas viram mensagem clara na tela, nunca tela branca ou travamento:

- **Timeout curto de conexão.** O cliente MongoDB usa `serverSelectionTimeoutMS`
  de 5s — se o Atlas estiver fora do ar, o erro aparece em segundos, em vez de
  esperar o padrão de 30s do driver.
- **Classificação de erro no backend.** Um único ponto traduz cada falha em uma
  mensagem específica: Voyage em limite de requisições, serviço de IA
  indisponível (chaves), índice de busca ausente e Atlas indisponível. O `/ask`
  responde `503` com essa mensagem.
- **Erro no streaming.** O `/ask/stream` **sempre** encerra com um evento `erro`
  quando algo falha — inclusive se o Claude cair no meio da redação: os tokens já
  enviados permanecem na tela e a mensagem explica a parada, sem corte silencioso.

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

## Limitações conhecidas

- **`per_cpu` não fecha "sockets consumidos vs. licenciados".** O campo
  `licenses.metric` (`per_cpu | per_host | per_user`) é hoje **descritivo**: o
  custo é sempre `unit_cost × quantity`, independente da métrica. Seria natural
  cruzar `servers.cpu_sockets` com uma licença `per_cpu`, mas o modelo não
  permite: `servers` conhece o `project_id`, **não** a `license_id`. Como um
  projeto tem várias licenças e vários servidores, somar sockets por projeto não
  atribui consumo a uma licença específica. Fechar isso exige um vínculo
  `servers → licenses` — registrado como fora de escopo (SPEC §8). Enquanto não
  existe, o sistema **não estima** esse número: a resposta honesta é dizer que o
  dado não existe.

## Segurança

- O `.env` (com a connection string do Atlas e as chaves de IA) **nunca**
  é versionado — está no `.gitignore`.
- Apenas o `.env.example` (sem valores reais) vai para o repositório.
- O `.gitignore` também exclui chaves/certificados (`*.pem`, `*.key`,
  `credentials*`, `secrets*`, etc.), `node_modules/`, `.venv/` e temporários.
