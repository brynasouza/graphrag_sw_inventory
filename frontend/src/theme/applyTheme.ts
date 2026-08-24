/**
 * Aplica o tema (theme.ts) ao app.
 *
 * Converte cada cor em uma variável CSS no elemento <html>, para que o
 * CSS (index.css) possa usar var(--color-primary), etc. Também ajusta o
 * título da aba com o nome da marca. Chamado uma vez em main.tsx.
 */
import { theme } from "./theme";

// camelCase -> kebab-case (primaryHover -> primary-hover)
function toKebab(s: string): string {
  return s.replace(/[A-Z]/g, (m) => "-" + m.toLowerCase());
}

export function applyTheme(): void {
  const root = document.documentElement;

  Object.entries(theme.colors).forEach(([nome, valor]) => {
    root.style.setProperty(`--color-${toKebab(nome)}`, valor);
  });
  root.style.setProperty("--radius", theme.radius);

  document.title = theme.brand.name;
}
