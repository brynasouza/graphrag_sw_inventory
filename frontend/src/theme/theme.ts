/**
 * ARQUIVO ÚNICO DE TEMA (re-tematização).
 *
 * Para adaptar o app a um novo cliente, edite SOMENTE este arquivo:
 *   1. Troque o nome e o logo em `brand`.
 *   2. Troque as cores em `colors`.
 * Nada mais precisa mudar — as cores viram variáveis CSS aplicadas em
 * todo o app (veja applyTheme.ts) e o logo aparece no cabeçalho.
 *
 * O logo pode ser:
 *   - uma URL ("https://.../logo.svg"),
 *   - um arquivo na pasta public ("/logo.svg"), ou
 *   - um data URI embutido (como o exemplo abaixo — 100% autocontido).
 */
export const theme = {
  brand: {
    name: "MVP GraphRAG",
    // Logo padrão embutido (um "nó de grafo" simples). Troque à vontade.
    logo:
      "data:image/svg+xml;utf8," +
      encodeURIComponent(
        `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" fill="none">
           <circle cx="24" cy="12" r="6" fill="#4f46e5"/>
           <circle cx="12" cy="36" r="6" fill="#06b6d4"/>
           <circle cx="36" cy="36" r="6" fill="#06b6d4"/>
           <path d="M24 18 L12 30 M24 18 L36 30" stroke="#94a3b8" stroke-width="2"/>
         </svg>`
      ),
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

  // Arredondamento padrão dos cantos.
  radius: "12px",
} as const;

export type Theme = typeof theme;
