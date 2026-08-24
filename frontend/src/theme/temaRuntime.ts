/**
 * Camada de tema em TEMPO DE EXECUÇÃO.
 *
 * O theme.ts é a fonte do PADRÃO. Aqui guardamos os AJUSTES que o usuário
 * faz no painel de personalização (nome, logo, cores, paleta, etc.) e
 * compomos o "tema efetivo" = padrão + ajustes.
 *
 * Os ajustes ficam SÓ no navegador (localStorage). Nunca vão para o código
 * nem para o backend. Por isso o repositório mantém o logo placeholder.
 */
import { PresetId, TipoGrafo, Theme, presets, theme } from "./theme";

// Chave do localStorage onde os ajustes ficam salvos.
export const CHAVE_TEMA = "inventario:tema";

/**
 * Ajustes que o painel pode aplicar. Tudo é opcional: o que não estiver
 * aqui usa o padrão do theme.ts.
 */
export interface Ajustes {
  presetId?: PresetId; // paleta escolhida (troca cores + cores dos nós)
  brandName?: string; // nome da aplicação
  logo?: string; // URL ou data URL (upload) do logo
  logoHeight?: string; // ex.: "36px"
  primary?: string; // cor primária (sobrescreve a da paleta)
  accent?: string; // cor de destaque (sobrescreve a da paleta)
  labelsSempre?: TipoGrafo[]; // tipos com rótulo sempre visível
}

/** Lê os ajustes salvos no navegador (ou {} se não houver / inválido). */
export function carregar(): Ajustes {
  try {
    const bruto = localStorage.getItem(CHAVE_TEMA);
    return bruto ? (JSON.parse(bruto) as Ajustes) : {};
  } catch {
    return {};
  }
}

/** Salva os ajustes no navegador. */
export function salvar(a: Ajustes): void {
  try {
    localStorage.setItem(CHAVE_TEMA, JSON.stringify(a));
  } catch {
    /* localStorage cheio/indisponível: ignora silenciosamente */
  }
}

/** Apaga os ajustes (volta ao padrão do theme.ts). */
export function limpar(): void {
  try {
    localStorage.removeItem(CHAVE_TEMA);
  } catch {
    /* ignora */
  }
}

/**
 * Compõe o TEMA EFETIVO a partir dos ajustes:
 *   (1) começa no padrão do theme.ts;
 *   (2) se houver `presetId`, aplica a paleta (cores + cor de cada nó);
 *   (3) aplica sobrescritas individuais (primary/accent/nome/logo/etc.).
 */
export function temaEfetivo(a: Ajustes): Theme {
  // (1) parte do padrão. Cópias rasas para não mutar o objeto original.
  const preset = a.presetId ? presets[a.presetId] : presets.indigo;

  const colors = { ...theme.colors, ...preset.colors };

  // (2) cor de cada tipo de nó vem da paleta; o rótulo continua do theme.ts.
  const graph = {} as Theme["graph"];
  (Object.keys(theme.graph) as TipoGrafo[]).forEach((tipo) => {
    graph[tipo] = {
      label: theme.graph[tipo].label,
      color: preset.graphColors[tipo],
    };
  });

  // (3) sobrescritas individuais por cima da paleta.
  if (a.primary) {
    colors.primary = a.primary;
    colors.primaryHover = a.primary; // simplificação: hover = primária escolhida
  }
  if (a.accent) {
    colors.accent = a.accent;
  }

  return {
    brand: {
      name: a.brandName?.trim() || theme.brand.name,
      logo: a.logo?.trim() || theme.brand.logo,
      logoHeight: a.logoHeight?.trim() || theme.brand.logoHeight,
    },
    colors,
    graph,
    labelsSempre: a.labelsSempre ?? theme.labelsSempre,
    layout: theme.layout,
    radius: theme.radius,
  };
}
