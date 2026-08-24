/**
 * ARQUIVO ÚNICO DE TEMA (re-tematização).
 *
 * Para adaptar o app a um novo cliente, edite SOMENTE este arquivo:
 *   1. Troque o nome e o logo em `brand`.
 *   2. Troque as cores em `colors`.
 *   3. (Opcional) Ajuste as cores dos nós do grafo em `graph`.
 * Nada mais precisa mudar — as cores viram variáveis CSS aplicadas em
 * todo o app (veja applyTheme.ts) e o logo/nome aparecem na barra lateral.
 *
 * O logo pode ser:
 *   - uma URL ("https://.../logo.svg"),
 *   - um arquivo na pasta public ("/logo.svg"), ou
 *   - um data URI embutido (como o padrão abaixo — 100% autocontido).
 */

// Logo PADRÃO: um "nó de grafo" neutro, embutido como SVG (data URI).
// É genérico de propósito — sem marca de terceiro — porque o projeto é
// público no GitHub. Troque pela marca do seu cliente à vontade.
const LOGO_PADRAO =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" fill="none">
       <circle cx="24" cy="12" r="6" fill="#4f46e5"/>
       <circle cx="12" cy="36" r="6" fill="#06b6d4"/>
       <circle cx="36" cy="36" r="6" fill="#06b6d4"/>
       <path d="M24 18 L12 30 M24 18 L36 30" stroke="#94a3b8" stroke-width="2"/>
     </svg>`
  );

export const theme = {
  brand: {
    // Nome da aplicação: usado em TODO lugar (título da aba e barra lateral).
    name: "Inventário de Software",
    // Logo exibido na barra lateral.
    logo: LOGO_PADRAO,
    // Altura do logo:
    //   - um valor fixo ("40px", "2.5rem", "64px") CONTROLA o tamanho;
    //   - "auto" RESPEITA o tamanho ORIGINAL da imagem.
    // A largura se ajusta sozinha (mantém a proporção, sem distorcer).
    logoHeight: "36px",
  },

  // Paleta de cores. Cada chave vira uma variável CSS: --color-primary etc.
  colors: {
    primary: "#4f46e5",       // cor principal (botões, destaques)
    primaryHover: "#4338ca",  // cor principal ao passar o mouse
    accent: "#06b6d4",        // cor de apoio
    background: "#f8fafc",    // fundo da página
    surface: "#ffffff",       // fundo de cartões
    text: "#0f172a",          // texto principal
    textMuted: "#64748b",     // texto secundário
    border: "#e2e8f0",        // linhas e bordas
    danger: "#dc2626",        // erros
  },

  // Cores dos NÓS do grafo, por tipo de entidade. `label` é o nome amigável
  // que aparece na legenda; `color` é a cor do ponto no grafo.
  graph: {
    vendor:      { label: "Fornecedor",      color: "#4f46e5" },
    product:     { label: "Produto",         color: "#7c3aed" },
    contract:    { label: "Contrato",        color: "#0ea5e9" },
    license:     { label: "Licença",         color: "#06b6d4" },
    project:     { label: "Projeto",         color: "#10b981" },
    team:        { label: "Time",            color: "#f59e0b" },
    cost_center: { label: "Centro de custo", color: "#ef4444" },
    server:      { label: "Servidor",        color: "#64748b" },
  },

  // Arredondamento padrão dos cantos.
  radius: "12px",
} as const;

export type Theme = typeof theme;
