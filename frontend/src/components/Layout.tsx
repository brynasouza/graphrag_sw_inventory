/**
 * Estrutura do app: barra lateral (marca + navegação) e área de conteúdo.
 *
 * A marca (logo + nome) vem do theme.ts, então a re-tematização continua
 * em um único arquivo. As páginas aparecem no <Outlet/>.
 */
import { NavLink, Outlet } from "react-router-dom";

import { theme } from "../theme/theme";

const LINKS = [
  { to: "/", rotulo: "Perguntar", fim: true },
  { to: "/painel", rotulo: "Painel", fim: false },
  { to: "/grafo", rotulo: "Explorar Grafo", fim: false },
];

export function Layout() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <img
            src={theme.brand.logo}
            alt={theme.brand.name}
            style={{ height: theme.brand.logoHeight }}
          />
          <span className="brand-name">{theme.brand.name}</span>
        </div>

        <nav className="nav">
          {LINKS.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.fim}
              className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
            >
              {l.rotulo}
            </NavLink>
          ))}
        </nav>
      </aside>

      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
