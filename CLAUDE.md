# CLAUDE.md

Convenções deste projeto. Leia antes de propor ou escrever qualquer coisa.

---

## Contexto de quem toca neste projeto

Solutions Architect com domínio de arquitetura e MongoDB, **iniciante em desenvolvimento**.
Explique decisões em linguagem simples, sem jargão desnecessário. Quando houver escolha
técnica, diga o porquê — não só o quê.

Este sistema é usado em **demonstrações para clientes enterprise**. Isso significa que
robustez visual e credibilidade dos números importam tanto quanto o código funcionar.

---

## Antes de escrever código

Leia o `SPEC.md`. Ele documenta o modelo de dados e as decisões de arquitetura com suas
justificativas. Se a mudança pedida contradiz algo lá, **diga isso antes de implementar**.

Para mudanças estruturais, apresente o plano e espere aprovação. Para ajustes pequenos
(um valor, uma cor, um rótulo), pode executar direto.

---

## Regras que não se negociam

**Segredos nunca entram no repositório.**
`.env` está no `.gitignore` e permanece lá. O que vai versionado é o `.env.example` com
valores falsos. Antes de qualquer `git push`, confirme que `git status` não lista o `.env`.

**Nenhuma marca de terceiro no código versionado.**
O `theme.ts` mantém logo placeholder genérico e paleta padrão. Logos de cliente são
carregados em tempo de execução pelo painel de personalização e vivem apenas no
`localStorage` do navegador.

**Nenhuma cor fixa dentro de componente.**
Todo valor visual — cor, largura, tamanho de fonte, altura de logo — vem do tema. O caminho
é `theme.ts → applyTheme.ts` (injeta variável CSS) → `index.css` (consome via `var(...)`).
Componentes leem via `useTheme()`. Se você precisar de um valor visual novo, adicione-o ao
`theme.ts` primeiro.

**O grafo garante os fatos; o LLM garante a linguagem.**
O modelo recebe contexto já estruturado e o *system prompt* proíbe inventar números ou
datas. Se um dado não existe no banco, a resposta correta é dizer que não existe — nunca
estimar.

**`$lookup` encadeado, não `$graphLookup`.**
Veja a justificativa no `SPEC.md`, seção 4. `$graphLookup` só se aplicaria se alguma
coleção ganhasse auto-referência.

---

## Estrutura

```
backend/app/
  api/         rotas HTTP
  core/        config e conexão com o Mongo
  models/      schemas Pydantic
  graph/       travessia de relacionamentos e agregações de custo
  retrieval/   busca vetorial e montagem de contexto
  llm/         geração da resposta final com o Claude
  ingestion/   seed e geração de embeddings
frontend/src/
  theme/       theme.ts — único lugar com valores visuais
  components/  Layout, GraphView, painel de personalização
  pages/       Home (Perguntar), Painel, ExplorarGrafo
```

---

## Como rodar

Dois processos, em terminais separados:

```bash
# backend — porta 8000
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload

# frontend — porta 5173
cd frontend && npm run dev
```

Se der `Address already in use`, o servidor já está rodando. Para derrubar:
`lsof -ti:8000 | xargs kill`

---

## Testes

```bash
cd backend && .venv/bin/python -m pytest -q
```

Testes que dependem da Voyage AI **pulam** em erro 503 em vez de falhar — instabilidade de
rede externa não é bug de código. Mas se o mesmo teste pular repetidamente, investigue:
pode ser problema de retry ou timeout disfarçado de rede.

Os três testes das perguntas-alvo são a verificação central. Se eles quebrarem, algo
importante quebrou.

---

## Personalização em tempo de execução

Painel abre com `Shift+P` ou pelo ícone de paleta na sidebar.
Preferências ficam no `localStorage`, chave `inventario:tema`.

Para limpar: botão "Restaurar padrão" no painel, ou
`localStorage.removeItem('inventario:tema')` no console.

**Sempre restaure o padrão antes de um `git push`** — garante que nenhuma marca de cliente
ficou salva na sessão.

---

## Pendências conhecidas

- `servers` não tem vínculo com `licenses`. Enquanto isso não existir, "sockets consumidos
  vs. sockets licenciados" não fecha.
- O aviso do Vite sobre bundle > 500 KB é esperado (peso do `react-force-graph`) e benigno.
  *Lazy load* resolveria, mas é desnecessário em demo local.
