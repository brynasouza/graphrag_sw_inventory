# CLAUDE.md

Convenções deste projeto. Leia antes de propor ou escrever qualquer coisa.

## O que é

**MVP de GraphRAG para gestão de inventário de software corporativo.** Responde perguntas
de negócio em linguagem natural sobre licenças, fornecedores, contratos, projetos e custos,
combinando um grafo de relacionamentos no MongoDB Atlas com busca vetorial e um LLM.

Endereça uma dor real de clientes enterprise: perder o controle do próprio inventário —
o que expira, quem é impactado, quanto se gasta — quando as respostas dependem de *relações*,
não de documentos isolados. É um MVP construído sobre um caso de uso de cliente real e usado
em demonstrações enterprise; portanto, robustez visual e credibilidade dos números importam
tanto quanto o código funcionar.

## Como trabalhar aqui

- Leia o `SPEC.md` antes de codar — ele traz o modelo de dados e as decisões com suas
  justificativas. Se o pedido contradiz algo lá, sinalize antes de implementar.
- Mudança estrutural: apresente o plano e espere aprovação. Ajuste pequeno (valor, cor,
  rótulo): execute direto.
- Ao propor uma escolha técnica, explique o *porquê* em linguagem direta, não só o *quê*.

## Decisões de arquitetura fixas

| Camada | Decisão |
|---|---|
| Banco | MongoDB Atlas + Atlas Vector Search |
| Modelo de dados | Grafo-nativo auto-referencial: coleção única `graph` (nós com arestas de saída embutidas), percorrida por `$graphLookup` — **zero `$lookup`** |
| Backend | Python 3.9+ · FastAPI · `pymongo` (driver síncrono) |
| Embeddings | Voyage AI `voyage-3.5` · 1024 dimensões · índice `vector_index` |
| LLM | Anthropic Claude `claude-sonnet-5` (configurável via `.env`) |
| Frontend | React 18 + TypeScript + Vite · grafo em `react-force-graph-2d` |

Versões exatas são fixadas em `backend/requirements.txt` e `frontend/package.json` — a tabela
registra as escolhas, os arquivos são a fonte da verdade.

## Regras inegociáveis

- **Segredos fora do repositório.** `.env` fica no `.gitignore`; versionado é só o
  `.env.example` com valores falsos. Antes de `git push`, confirme que `git status` não lista `.env`.
- **Nenhuma marca de terceiro versionada.** `theme.ts` usa logo placeholder e paleta padrão.
  Logos de cliente entram em runtime pelo painel e vivem só no `localStorage`.
- **Nenhum valor visual fixo em componente.** Cor, largura, fonte, altura de logo — tudo vem
  do tema: `theme.ts → applyTheme.ts` (injeta CSS var) → `index.css` (`var(...)`), lido via
  `useTheme()`. Valor visual novo? Adicione ao `theme.ts` primeiro.
- **Travessia com `$graphLookup` sobre coleção auto-referencial — ZERO `$lookup`.** Recursa
  DENTRO de `graph` por `connectFromField:"arestas.to" → connectToField:"_id"`; cada nó
  devolvido já traz `label`/`props`, então rótulo sai direto (filtra por `tipo`, lê `.label`) —
  sem `$lookup` para hidratar. Reversa (servidor→projeto, produto→fornecedor): inverte os
  campos ou usa `$elemMatch`. `restrictSearchWithMatch` filtra o NÓ-alvo por `tipo`. Nenhum
  pipeline pode reintroduzir `$lookup` (é o critério de aceite do rewrite; há teste que trava).
  Tradeoffs no `SPEC.md` §4.

## Contratos (não quebrar)

- **O grafo garante os fatos; o LLM garante a linguagem.** O modelo recebe contexto
  estruturado e o *system prompt* proíbe inventar número ou data. Dado ausente no banco →
  a resposta é dizer que não existe, nunca estimar.
- **O comando exibido é o que de fato roda.** O painel "Ver a consulta" mostra o pipeline
  MongoDB real, montado num builder único reaproveitado por execução e exibição — nunca um
  pipeline "de vitrine". GETs: opt-in `?incluir_consulta=true` (sem ele, resposta inalterada,
  por isso os testes seguem verdes). `/ask`: em `context.consultas`.

## Estrutura

```
backend/app/
  api/         rotas HTTP
  core/        config e conexão com o Mongo
  models/      schemas Pydantic
  graph/       travessia e agregações de custo
  retrieval/   busca vetorial e montagem de contexto
  llm/         geração da resposta com o Claude
  ingestion/   seed e embeddings
frontend/src/
  theme/       theme.ts — único lugar com valores visuais
  components/  Layout, GraphView, painel de personalização
  pages/       Perguntar, Painel, ExplorarGrafo
```

## Comandos

```bash
# backend (porta 8000) e frontend (porta 5173) — terminais separados
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload
cd frontend && npm run dev

# testes
cd backend && .venv/bin/python -m pytest -q
```

`Address already in use` = servidor já rodando; derrube com `lsof -ti:8000 | xargs kill`.
Os três testes das perguntas-alvo são a verificação central — se quebrarem, algo importante
quebrou. Testes que dependem da Voyage AI **pulam** em erro 503 (rede externa não é bug);
se pularem repetidamente, investigue retry/timeout disfarçado de rede.

## Seed e embeddings

- `seed.py` é **determinístico** (`_id` derivado de chave natural via `oid_estavel`) e usa
  datas **relativas** à data-base (env `SEED_DATA_BASE`) — para "vence em 90 dias" seguir real.
- Seed **não** toca em `search_index`; quem reconstrói é o `build_embeddings.py`. Rode-o de
  novo só quando entidades ou seus textos mudarem, não a cada seed.
- O texto vetorizado tem **âncora funcional** (`_DESCRICAO_FUNCIONAL`) só em OpenShift,
  Confluence, Jira e Microsoft 365, para perguntas por conceito resolverem com folga. A âncora
  vive **apenas** no texto indexado, nunca nos campos de negócio (um `find()` continua não
  achando — é essa a diferença que a busca vetorial prova). Mudou uma frase? Rode de novo.

## Personalização em runtime

Painel: `Shift+P` ou ícone de paleta. Preferências no `localStorage`, chave `inventario:tema`.
Limpar: botão "Restaurar padrão" ou `localStorage.removeItem('inventario:tema')`.
**Restaure o padrão antes de `git push`** — garante que nenhuma marca de cliente ficou salva.

## Pendências conhecidas

- `servers` sem vínculo com `licenses` → "sockets consumidos vs. licenciados" não fecha.
- Aviso do Vite de bundle > 500 KB (peso do `react-force-graph`) é esperado e benigno.
</content>
