# SPEC — Inventário de Software com GraphRAG

> Especificação retroativa. Documenta **o que** o sistema faz e **por quê** as decisões
> de arquitetura foram tomadas. O código implementa esta especificação; quando os dois
> divergirem, esta especificação é o ponto de partida da conversa.

---

## 1. Problema

Empresas de médio e grande porte perdem o controle do próprio inventário de software.
As perguntas que importam não são sobre um documento isolado — são sobre **relações**:

- Quais projetos usam a licença da VMware e quando ela expira?
- Se a licença X expirar, quais times são impactados?
- Quanto gastamos com o fornecedor Y, quebrado por centro de custo?

Nenhuma dessas perguntas é respondida por busca por similaridade de texto. Todas exigem
percorrer relacionamentos e fazer contas. Esse é o motivo de o sistema ser GraphRAG e
não RAG comum.

## 2. Requisitos funcionais

| # | Requisito | Como se verifica |
|---|---|---|
| RF-1 | Responder em linguagem natural às três perguntas-alvo acima | Teste automatizado em `tests/test_ask.py` |
| RF-2 | Nunca inventar números ou datas ausentes no banco | O *system prompt* proíbe; observado na prática (o modelo se recusa a chutar) |
| RF-3 | Exibir o subgrafo usado para chegar a cada resposta | Mini-grafo na tela "Perguntar"; `context.subgrafo` na resposta da API |
| RF-4 | Navegar o inventário inteiro como grafo interativo | Tela "Explorar Grafo" |
| RF-5 | Exibir painel com licenças vencendo e gastos agregados | Tela "Painel" |
| RF-6 | Re-tematizar (logo, cores, nome) sem alterar código | `theme.ts` + painel de personalização (`Shift+P`) |
| RF-7 | Não conter marca de terceiro no repositório | `theme.ts` versionado usa logo placeholder |

## 3. Requisitos não funcionais

- **Segredos fora do versionamento.** Connection string e chaves de API vivem no `.env`,
  ignorado pelo git. O repositório contém apenas `.env.example`.
- **Zero vulnerabilidades no `npm audit`** como condição de publicação.
- **Nenhuma cor fixa dentro de componente.** Todo valor visual vem do tema.
- **Personalização não persiste no repositório.** Ajustes de demo vivem no `localStorage`
  do navegador, nunca no código.

---

## 4. Modelo de dados

Nove coleções no MongoDB, ligadas por referência (`_id` do vizinho), não por aninhamento.
Referência permite percorrer o relacionamento em qualquer direção sem duplicar dados.

| Coleção | Campos-chave |
|---|---|
| `vendors` | `name` |
| `products` | `vendor_id` → vendors, `name` |
| `contracts` | `vendor_id` → vendors, `reference`, `value`, `currency`, `starts_at`, `ends_at` |
| `licenses` | `product_id`, `contract_id`, `name`, `expires_at`, `unit_cost`, `currency`, `metric` |
| `allocations` | `license_id`, `project_id`, `quantity`, `allocated_at` |
| `projects` | `team_id` → teams, `name` |
| `teams` | `cost_center_id` → cost_centers, `name` |
| `cost_centers` | `name`, `code` |
| `servers` | `hostname`, `cpu_sockets`, `project_id` |

Mais uma coleção auxiliar: `search_index`, que guarda os *embeddings*. Cada documento tem
`entity_type` ("license" ou "vendor"), `entity_id` (referência à entidade indexada), `name`,
`text` (a frase descritiva que foi vetorizada) e `embedding` (vetor de 1024 floats). Só
licenças e fornecedores são indexados.

### Decisões e justificativas

**`$lookup` encadeado, não `$graphLookup`.**
`$graphLookup` faz travessia recursiva dentro de **uma** coleção auto-referenciada, com
profundidade variável — hierarquias do tipo "funcionário → gerente → gerente do gerente".
O caminho deste sistema (`licenses → allocations → projects → teams → cost_centers`)
atravessa coleções **diferentes** com profundidade **fixa e conhecida**. Isso é `$lookup`
encadeado, um join por salto no pipeline de agregação.

`$graphLookup` só passaria a fazer sentido se alguma coleção ganhasse auto-referência —
por exemplo, `cost_centers` ou `teams` com um `parent_id` formando hierarquia de N níveis.
Fica registrado como opção futura.

**`allocations` é coleção, não array dentro de `projects`.**
A relação licença ↔ projeto é muitos-para-muitos **com atributos próprios**. Um array de
`license_ids` em `projects` responderia "quais licenças este projeto usa", mas quebraria em
três pontos: a pergunta inversa fica cara, não há onde guardar a **quantidade** consumida,
e sem quantidade não há como ratear custo. Modelada como coleção-ponte (tabela de arestas
do grafo), os três problemas somem.

**`unit_cost` fica em `licenses`, não só `value` em `contracts`.**
"Quanto gastamos por centro de custo" exige custo **por licença**, multiplicado pela
quantidade alocada. O valor do contrato inteiro não desce até o centro de custo.
A cadeia que fecha a conta: `licenses.unit_cost` × `allocations.quantity`, agregado por
`cost_centers`.

**`servers` existe porque VMware é licenciado por host/CPU.**
Sem uma entidade de servidor, o caso de uso mais realista do inventário (consumo de sockets
vs. sockets licenciados) fica de fora.

**`search_index` é coleção separada, não vetor dentro de `licenses`.**
Mantém os documentos de negócio limpos, permite indexar tipos diferentes (licenças *e*
fornecedores) num só índice, e o índice pode ser reconstruído a qualquer momento sem tocar
nos dados. A reconstrução é **incremental** (`build_embeddings.py`): só re-embedda o texto
que mudou, reaproveita o resto e remove órfãos — rodar de novo sem mudança não gasta cota
da Voyage.

### Métricas de licenciamento (`licenses.metric`)

Cada licença declara **como é cobrada**:

| Métrica | Significado |
|---|---|
| `per_cpu` | licenciada por CPU/soquete (ex.: virtualização por host) |
| `per_host` | licenciada por servidor/host |
| `per_user` | licenciada por usuário nomeado |

Hoje `metric` é **descritiva**: o custo é sempre `unit_cost × allocations.quantity`,
**independente da métrica**. A `quantity` da alocação já carrega o número contratado
(CPUs, hosts ou usuários), então a conta fecha sem multiplicar pela métrica.

**Por que `cpu_sockets` (de `servers`) não entra no cálculo `per_cpu`.** Seria natural
querer "sockets consumidos vs. sockets licenciados", mas o modelo atual **não fecha** essa
conta: `servers` conhece o `project_id`, não a `license_id`. Como um projeto tem várias
licenças e vários servidores, somar os `cpu_sockets` de um projeto **não** atribui consumo
a uma licença específica. Fechar isso exige um vínculo `servers → licenses` — registrado
como fora de escopo na seção 8. Enquanto ele não existe, o sistema **não** insinua esse
número: a resposta honesta é dizer que o dado não existe, não estimá-lo.

### Fronteira ObjectId × string

Dentro do MongoDB (e dos pipelines de agregação), `_id` e todas as chaves estrangeiras são
**ObjectId**. Na borda HTTP/JSON, viram **string**. A conversão acontece em um ponto de
cada lado — nunca espalhada pelo código:

- **entrada** (str → ObjectId): `to_object_id()` em `app/graph/queries.py`;
- **saída** (ObjectId → str): `_clean()` (queries.py), `$toString` nos `$project` e
  `str(_id)` no `GraphBuilder` (`app/graph/graphdata.py`).

Os modelos Pydantic (`app/models/schemas.py`) tipam as FKs como `str` porque documentam a
forma **exposta na API**. No banco elas são ObjectId; inserir uma FK como string crua
quebraria os `$lookup` (que casam ObjectId com ObjectId).

---

## 5. Como o GraphRAG funciona

Quatro passos, nesta ordem:

1. **Busca vetorial** identifica o nó de entrada a partir do texto livre. O usuário escreve
   "virtualização de servidores"; o sistema descobre que isso aponta para VMware/vSphere.
   Embeddings gerados pela Voyage AI (`voyage-3.5`, 1024 dimensões), índice
   `vector_index` no Atlas Vector Search.
2. **`$lookup` encadeado** expande as conexões a partir desse nó.
3. **Agregações** fazem as contas (`unit_cost` × `quantity`, somado por centro de custo).
4. **O LLM redige** a resposta a partir do contexto já estruturado.

A regra que governa a divisão de trabalho: **o grafo garante os fatos; o LLM garante a
linguagem.** O modelo recebe os dados prontos e não tem permissão para preencher lacunas.

> ⚠️ Ponto de atenção conhecido: a busca vetorial resolvia "VMware" para as *licenças*
> (cujo texto cita VMware) e não para o *fornecedor*, deixando a pergunta de custo sem
> números. Corrigido: ao encontrar uma licença, o contexto também descobre o fornecedor
> dela e anexa o gasto por centro de custo.

### Formato canônico do grafo

```
node = { "id": str,
         "tipo": "vendor|product|contract|license|project|team|cost_center|server",
         "label": str,
         "props": { ... } }

edge = { "source": str, "target": str, "tipo": str, "label": str|None }
```

`allocations` **não vira nó** — vira uma aresta `license → project` com a quantidade no
rótulo. Se cada alocação fosse um nó, o grafo ficaria poluído com pontos sem significado
visual.

---

## 6. Arquitetura

```
frontend (React + TypeScript + Vite, porta 5173)
    ↓ HTTP
backend  (FastAPI + Python, porta 8000)
    ↓
MongoDB Atlas  ──  Voyage AI (embeddings)  ──  Anthropic API (redação)
```

**Backend** — `app/api` (rotas), `app/core` (config e conexão), `app/models` (schemas
Pydantic), `app/graph` (travessia e agregações), `app/retrieval` (vetorial e montagem de
contexto), `app/llm` (redação da resposta final com o Claude), `app/ingestion` (seed e
embeddings).

**Frontend** — três rotas: `/` (Perguntar), `/painel` (Painel), `/grafo` (Explorar Grafo).
Grafo renderizado com `react-force-graph-2d`, escolhido por usar simulação de física: os
nós se organizam sozinhos e o resultado comunica "rede de relacionamentos" de relance, o
que fluxograma estático não faz.

**Tema** — o tema efetivo é `theme.ts` (padrão versionado) **sobrescrito** pelos ajustes
salvos no navegador. Caminho: `theme.ts → applyTheme.ts` injeta variáveis CSS →
`index.css` consome via `var(...)`. Componentes leem via `useTheme()`.

Grupos configuráveis no `theme.ts`: `brand` (nome, logo, altura), `colors` (paleta),
`graph` (cor por tipo de entidade), `labelsSempre` (tipos de nó com rótulo sempre
visível), `layout` (largura da sidebar, tamanho da fonte da marca) e `radius`
(arredondamento dos cantos). Presets nomeados: Índigo (padrão), Roxo, Esmeralda.

---

## 7. Escolhas deliberadas de sequência

A ordem de construção foi: dados → travessia sem IA → agregações → vetorial → GraphRAG
completo → interface.

O motivo de a IA vir **por último**: se o grafo estiver errado, o erro aparece num
resultado que dá para conferir na mão. Com o LLM no meio desde o início, o erro fica
escondido atrás de um texto bem escrito.

---

## 8. Fora de escopo (por enquanto)

- Autenticação e controle de acesso
- Ingestão automática a partir de fontes reais (hoje os dados são *seed* sintético)
- Vínculo entre `servers` e `licenses` — hoje o servidor conhece o projeto, mas não a
  licença que consome. Sem isso, "sockets consumidos vs. sockets licenciados" não fecha.
- *Lazy load* da biblioteca de grafo (bundle de ~533 KB; irrelevante em demo local)
- Deploy — o sistema roda apenas em máquina local
