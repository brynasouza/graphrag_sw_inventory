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

Modelo **grafo-nativo auto-referencial**: uma coleção única `graph`, onde cada documento é
uma entidade **com suas arestas de saída embutidas**. É o padrão canônico que o operador de
grafo do MongoDB (`$graphLookup`) percorre — recursando *dentro da própria coleção*, sem
nenhum `$lookup`. Toda entidade do inventário é um **nó**; cada relacionamento *downstream*
vive no array `arestas` do nó de origem.

| Coleção | Campos | Observação |
|---|---|---|
| `graph` | `_id`, `tipo`, `label`, `props`, `arestas` | `tipo` ∈ {vendor, product, contract, license, project, team, cost_center, server}; `props` guarda os campos de negócio (`unit_cost`, `currency`, `expires_at`, `metric`, `code`, `hostname`, `cpu_sockets`, `name`, …); `arestas` é a lista de arestas de saída `{to, tipo, props}` |

Cada item de `arestas` é `{to: <_id do nó destino>, tipo: <vínculo>, props: {…}}`. Os tipos
de aresta (sempre no sentido da travessia *downstream*, embutidos no nó de origem):

| `tipo` da aresta | De (nó dono) → Para (`to`) | `props` |
|---|---|---|
| `alocacao` | license → project | `quantity`, `allocated_at` |
| `projeto_time` | project → team | — |
| `time_centro` | team → cost_center | — |
| `licenca_produto` | license → product | — |
| `licenca_contrato` | license → contract | — |
| `produto_fornecedor` | product → vendor | — |
| `contrato_fornecedor` | contract → vendor | — |
| `servidor_projeto` | server → project | — |

A travessia *downstream* é `{from:"graph", startWith:"$arestas.to", connectFromField:"arestas.to",
connectToField:"_id"}`. Quando é preciso subir (ex.: servidores de um projeto, fornecedor de um
produto), a travessia **reversa** inverte os campos (`connectFromField:"_id"`,
`connectToField:"arestas.to"`) ou usa um `$elemMatch` em `arestas`.

O `_id` de cada nó é **determinístico**, derivado de uma chave natural namespaced por tipo
(`oid_estavel("license:vSphere Standard 2026")`). Isso mantém a `search_index` válida entre
seeds sem re-embeddar (ver adiante) e permite re-seedar sem quebrar referências.

Mais uma coleção auxiliar: `search_index`, que guarda os *embeddings*. Cada documento tem
`entity_type` ("license" ou "vendor"), `entity_id` (o `_id` do nó indexado), `name`,
`text` (a frase descritiva que foi vetorizada) e `embedding` (vetor de 1024 floats). Só
licenças e fornecedores são indexados.

### Decisões e justificativas

**Travessia com `$graphLookup` sobre coleção auto-referencial — zero `$lookup`.**
Cada nó carrega suas arestas de saída embutidas, então o `$graphLookup` recursa DENTRO da
própria coleção `graph`: `{from:"graph", startWith:"$arestas.to", connectFromField:"arestas.to",
connectToField:"_id"}`. Crucialmente, **cada documento devolvido pela travessia já é um nó
completo, com seu `label` e `props`** — então os rótulos dos nós finais saem direto do
resultado (filtrando por `tipo` e lendo `.label`), sem nenhum `$lookup` para hidratar. Essa é
a diferença central do rewrite: no modelo antigo (duas coleções `graph_nodes` + `graph_edges`)
a travessia devolvia só arestas `{from, to, tipo}` e 5 `$lookup` apareciam para resolver os
atributos — lidos no painel "Ver a consulta" como "ainda é join estilo SQL". Agora não há
nenhum. `restrictSearchWithMatch` continua podando a travessia, mas filtra o **nó alcançado**
(por `tipo`), não a aresta — equivalente aqui, porque cada salto cai num tipo de nó distinto
(`project → team → cost_center`, `product → vendor`).

> **Tradeoffs assumidos (registro honesto).** (1) Custo é agregação **ponderada por caminho**
> (`quantity × unit_cost`, somado por centro/moeda), e o `$graphLookup` coleta
> *alcançabilidade*, não soma pesos por aresta. Mas no modelo embutido o `spend` de cada
> alocação é **local**: `unit_cost` (campo do nó licença) × `quantity` (aresta `alocacao`
> embutida) vivem no MESMO documento, calculados antes de percorrer; o `$graphLookup` só
> resolve o nó final (fornecedor/centro). (2) A travessia **reversa** (servidor → projeto,
> produto/contrato → fornecedor) é menos natural que no grafo homogêneo — resolvida invertendo
> `connectFromField`/`connectToField` ou com `$elemMatch` em `arestas`. (3) A poda passou a ser
> por **tipo de nó**, não por tipo de aresta. Aceito de propósito: a demo é sobre o MongoDB
> **fazendo grafo** com `$graphLookup`, e agora o painel "Ver a consulta" não exibe um único
> `$lookup`. (Versões anteriores usaram `$lookup` encadeado e depois duas coleções homogêneas;
> ambas revertidas — ver `CLAUDE.md` e o histórico do repo.)

**`allocations` é aresta, não array dentro de `projects`.**
A relação licença ↔ projeto é muitos-para-muitos **com atributos próprios**. Um array de
`license_ids` em `projects` responderia "quais licenças este projeto usa", mas quebraria em
três pontos: a pergunta inversa fica cara, não há onde guardar a **quantidade** consumida,
e sem quantidade não há como ratear custo. Modelada como **aresta** `license → project`
(`tipo:"alocacao"`) carregando `quantity` em `props`, os três problemas somem — e é a
própria aresta que o grafo percorre.

**`unit_cost` fica no nó `license`, não só `value` no contrato.**
"Quanto gastamos por centro de custo" exige custo **por licença**, multiplicado pela
quantidade alocada. O valor do contrato inteiro não desce até o centro de custo.
A cadeia que fecha a conta: `license.props.unit_cost` × `props.quantity` da aresta
`alocacao`, agregado por nó `cost_center`.

**O nó `server` existe porque VMware é licenciado por host/CPU.**
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

Hoje `metric` é **descritiva**: o custo é sempre `unit_cost` (nó licença) × `quantity`
(aresta `alocacao`), **independente da métrica**. A `quantity` da aresta já carrega o número
contratado (CPUs, hosts ou usuários), então a conta fecha sem multiplicar pela métrica.

**Por que `cpu_sockets` (do nó `server`) não entra no cálculo `per_cpu`.** Seria natural
querer "sockets consumidos vs. sockets licenciados", mas o modelo atual **não fecha** essa
conta: a única aresta do servidor é `servidor_projeto` (server → project), não há aresta
`server → license`. Como um projeto tem várias licenças e vários servidores, somar os
`cpu_sockets` de um projeto **não** atribui consumo a uma licença específica. Fechar isso
exige uma aresta `server → license` — registrado como fora de escopo na seção 8. Enquanto
ela não existe, o sistema **não** insinua esse número: a resposta honesta é dizer que o dado
não existe, não estimá-lo.

### Fronteira ObjectId × string

Dentro do MongoDB (e dos pipelines de agregação), `_id` de nós e o campo `to` de cada aresta
embutida são **ObjectId**. Na borda HTTP/JSON, viram **string**. A conversão acontece em um
ponto de cada lado — nunca espalhada pelo código:

- **entrada** (str → ObjectId): `to_object_id()` em `app/graph/queries.py`;
- **saída** (ObjectId → str): `$toString` nos `$project` e `str(_id)`/`str(to)` no
  `GraphBuilder` (`app/graph/graphdata.py`).

Os modelos Pydantic (`app/models/schemas.py`) tipam `Aresta.to` como `str` porque documentam
a forma **exposta na API**. No banco é ObjectId; inserir um `to` como string crua quebraria o
`$graphLookup` (que casa `arestas.to` com `_id` por igualdade de ObjectId).

---

## 5. Como o GraphRAG funciona

Quatro passos, nesta ordem:

1. **Busca vetorial** identifica o nó de entrada a partir do texto livre. O usuário escreve
   "virtualização de servidores"; o sistema descobre que isso aponta para VMware/vSphere.
   Embeddings gerados pela Voyage AI (`voyage-3.5`, 1024 dimensões), índice
   `vector_index` no Atlas Vector Search.
2. **`$graphLookup`** percorre o grafo a partir desse nó, recursando na coleção `graph`
   pelas arestas embutidas (`arestas.to` → `_id`), sem nenhum `$lookup`.
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
- Aresta `server → license` — hoje o servidor só tem a aresta `servidor_projeto` (conhece o
  projeto, não a licença que consome). Sem ela, "sockets consumidos vs. sockets licenciados"
  não fecha.
- *Lazy load* da biblioteca de grafo (bundle de ~533 KB; irrelevante em demo local)
- Deploy — o sistema roda apenas em máquina local
