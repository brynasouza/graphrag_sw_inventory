/**
 * ARQUIVO ÚNICO DE TEMA (re-tematização).
 *
 * Este arquivo é a FONTE DO PADRÃO. Para adaptar o app a um novo cliente
 * de forma permanente, edite SOMENTE este arquivo:
 *   1. Troque o nome e o logo em `brand`.
 *   2. Troque as cores em `colors` (ou escolha outra paleta em `presets`).
 *   3. (Opcional) Ajuste os rótulos/cores dos nós do grafo em `graph`.
 *   4. (Opcional) Ajuste `labelsSempre` (quais tipos mostram rótulo sempre).
 *
 * Nada mais precisa mudar — as cores viram variáveis CSS aplicadas em todo
 * o app (veja applyTheme.ts) e o logo/nome aparecem na barra lateral.
 *
 * IMPORTANTE: o "Painel de Personalização" (ícone de paleta na sidebar)
 * consegue sobrescrever tudo isso EM TEMPO DE EXECUÇÃO, guardando os ajustes
 * no navegador (localStorage). Isso NÃO altera este arquivo — o que vai para
 * o GitHub continua com o logo placeholder e as cores padrão daqui.
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

// Os 8 tipos de entidade do grafo, na ordem em que aparecem na legenda.
export const TIPOS_GRAFO = [
  "vendor",
  "product",
  "contract",
  "license",
  "project",
  "team",
  "cost_center",
  "server",
] as const;

export type TipoGrafo = (typeof TIPOS_GRAFO)[number];

// Paleta da interface (as 9 cores). Cada chave vira uma variável CSS.
export interface Paleta {
  primary: string;
  primaryHover: string;
  accent: string;
  background: string;
  surface: string;
  text: string;
  textMuted: string;
  border: string;
  danger: string;
}

// Uma paleta pronta: cores da interface + cor de cada tipo de nó do grafo.
export interface Preset {
  nome: string;
  colors: Paleta;
  graphColors: Record<TipoGrafo, string>;
}

export interface Brand {
  name: string;
  logo: string;
  logoHeight: string;
}

// Medidas de layout configuráveis (largura da sidebar, tamanho do nome).
export interface Layout {
  sidebarWidth: string;
  brandFontSize: string;
}

// O TEMA (efetivo). É o que os componentes leem para desenhar.
export interface Theme {
  brand: Brand;
  colors: Paleta;
  graph: Record<TipoGrafo, { label: string; color: string }>;
  labelsSempre: TipoGrafo[];
  layout: Layout;
  radius: string;
}

// Ids das paletas prontas (usados pelo painel de personalização).
export type PresetId = "indigo" | "roxo" | "esmeralda";

/**
 * PALETAS PRONTAS ("presets").
 *
 * Cada paleta define `colors` (interface) e `graphColors` (cor de cada tipo
 * de nó). Os RÓTULOS dos tipos NÃO mudam entre paletas — ficam em
 * `graph[tipo].label` mais abaixo. O painel lista estas paletas pelo `nome`.
 */
export const presets: Record<PresetId, Preset> = {
  // Índigo — a paleta PADRÃO (é a que `theme.colors`/`theme.graph` usam).
  indigo: {
    nome: "Índigo (padrão)",
    colors: {
      primary: "#4f46e5",
      primaryHover: "#4338ca",
      accent: "#06b6d4",
      background: "#f8fafc",
      surface: "#ffffff",
      text: "#0f172a",
      textMuted: "#64748b",
      border: "#e2e8f0",
      danger: "#dc2626",
    },
    graphColors: {
      vendor: "#4f46e5",
      product: "#7c3aed",
      contract: "#0ea5e9",
      license: "#06b6d4",
      project: "#10b981",
      team: "#f59e0b",
      cost_center: "#ef4444",
      server: "#64748b",
    },
  },

  // Roxo — roxo escuro como primária, destaque magenta, fundo claro neutro.
  // Nós em tons de roxo -> magenta.
  roxo: {
    nome: "Roxo",
    colors: {
      primary: "#5b21b6",
      primaryHover: "#4c1d95",
      accent: "#d946ef",
      background: "#faf5ff",
      surface: "#ffffff",
      text: "#2e1065",
      textMuted: "#7c6f9b",
      border: "#e9d5ff",
      danger: "#dc2626",
    },
    graphColors: {
      vendor: "#4c1d95",
      product: "#6d28d9",
      contract: "#7c3aed",
      license: "#9333ea",
      project: "#a855f7",
      team: "#c026d3",
      cost_center: "#d946ef",
      server: "#8b5cf6",
    },
  },

  // Esmeralda — verde/teal, para dar uma escolha bem diferente na demo.
  esmeralda: {
    nome: "Esmeralda",
    colors: {
      primary: "#0f766e",
      primaryHover: "#115e59",
      accent: "#f59e0b",
      background: "#f0fdfa",
      surface: "#ffffff",
      text: "#042f2e",
      textMuted: "#5f7d78",
      border: "#ccfbf1",
      danger: "#dc2626",
    },
    graphColors: {
      vendor: "#0f766e",
      product: "#0d9488",
      contract: "#0891b2",
      license: "#14b8a6",
      project: "#22c55e",
      team: "#f59e0b",
      cost_center: "#ef4444",
      server: "#64748b",
    },
  },
};

// Paleta PADRÃO usada pelo app (= preset "indigo"). Trocar aqui muda o padrão.
const PRESET_PADRAO = presets.indigo;

export const theme: Theme = {
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

  // Paleta de cores da interface (= paleta padrão / preset "indigo").
  colors: { ...PRESET_PADRAO.colors },

  // Cores e RÓTULOS dos nós do grafo, por tipo de entidade. `label` é o nome
  // amigável (legenda); `color` é a cor do ponto. Os rótulos NÃO mudam ao
  // trocar de paleta.
  graph: {
    vendor: { label: "Fornecedor", color: PRESET_PADRAO.graphColors.vendor },
    product: { label: "Produto", color: PRESET_PADRAO.graphColors.product },
    contract: { label: "Contrato", color: PRESET_PADRAO.graphColors.contract },
    license: { label: "Licença", color: PRESET_PADRAO.graphColors.license },
    project: { label: "Projeto", color: PRESET_PADRAO.graphColors.project },
    team: { label: "Time", color: PRESET_PADRAO.graphColors.team },
    cost_center: { label: "Centro de custo", color: PRESET_PADRAO.graphColors.cost_center },
    server: { label: "Servidor", color: PRESET_PADRAO.graphColors.server },
  },

  // Tipos de nó que mostram o rótulo SEMPRE. Os demais só aparecem no hover,
  // quando selecionados, ou quando vizinhos de um nó selecionado. Isso evita
  // que os rótulos se sobreponham e fiquem ilegíveis. Configurável no painel.
  labelsSempre: ["vendor", "project"],

  // Medidas da barra lateral — ajuste aqui sem tocar em CSS/componente:
  //   - sidebarWidth: largura da barra lateral esquerda.
  //   - brandFontSize: tamanho do nome da aplicação na barra lateral.
  layout: {
    sidebarWidth: "264px",
    brandFontSize: "1.2rem",
  },

  // Arredondamento padrão dos cantos.
  radius: "12px",
};
