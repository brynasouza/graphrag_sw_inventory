/**
 * Aplica um TEMA (efetivo) ao app.
 *
 * Converte cada cor em uma variável CSS no elemento <html>, para que o
 * CSS (index.css) possa usar var(--color-primary), etc. Também ajusta o
 * título da aba com o nome da marca.
 *
 * Recebe o tema por PARÂMETRO (não lê o theme.ts direto) porque o tema pode
 * ter sido sobrescrito em tempo de execução pelo painel — veja ThemeContext.
 */
import { Theme } from "./theme";

// camelCase -> kebab-case (primaryHover -> primary-hover)
function toKebab(s: string): string {
  return s.replace(/[A-Z]/g, (m) => "-" + m.toLowerCase());
}

export function aplicarVars(tema: Theme): void {
  const root = document.documentElement;

  Object.entries(tema.colors).forEach(([nome, valor]) => {
    root.style.setProperty(`--color-${toKebab(nome)}`, valor);
  });
  root.style.setProperty("--radius", tema.radius);
  root.style.setProperty("--logo-height", tema.brand.logoHeight);
  root.style.setProperty("--sidebar-width", tema.layout.sidebarWidth);
  root.style.setProperty("--brand-font-size", tema.layout.brandFontSize);

  document.title = tema.brand.name;
}
