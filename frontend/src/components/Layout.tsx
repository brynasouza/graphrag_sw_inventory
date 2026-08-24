/**
 * Estrutura do app: barra lateral (marca + navegação + botão de tema) e
 * área de conteúdo.
 *
 * A marca (logo + nome) vem do TEMA EFETIVO (useTheme), então tanto a
 * re-tematização por código (theme.ts) quanto o painel de personalização
 * funcionam sem cor/valor fixo aqui. As páginas aparecem no <Outlet/>.
 *
 * Um botão discreto (ícone de paleta) no rodapé da sidebar abre o painel de
 * personalização. Atalho de teclado: Shift+P.
 */
import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { useTheme } from "../theme/ThemeContext";
import { PainelTema } from "./PainelTema";

const LINKS = [
  { to: "/", rotulo: "Perguntar", fim: true },
  { to: "/painel", rotulo: "Painel", fim: false },
  { to: "/grafo", rotulo: "Explorar Grafo", fim: false },
];

export function Layout() {
  const tema = useTheme();
  const [painelAberto, setPainelAberto] = useState(false);

  // Atalho de teclado: Shift+P abre/fecha o painel (ignora quando o foco
  // está num campo de texto, para não atrapalhar a digitação).
  useEffect(() => {
    function aoTeclar(e: KeyboardEvent) {
      const alvo = e.target as HTMLElement | null;
      const digitando =
        alvo && (alvo.tagName === "INPUT" || alvo.tagName === "TEXTAREA" || alvo.isContentEditable);
      if (e.shiftKey && (e.key === "P" || e.key === "p") && !digitando) {
        e.preventDefault();
        setPainelAberto((v) => !v);
      }
    }
    window.addEventListener("keydown", aoTeclar);
    return () => window.removeEventListener("keydown", aoTeclar);
  }, []);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <img
            src={tema.brand.logo}
            alt={tema.brand.name}
            style={{ height: tema.brand.logoHeight }}
          />
          <span className="brand-name">{tema.brand.name}</span>
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

        {/* Botão discreto de personalização (ícone de paleta). */}
        <button
          className="tema-botao"
          onClick={() => setPainelAberto(true)}
          title="Personalizar (Shift+P)"
          aria-label="Personalizar aparência"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
              d="M12 3a9 9 0 100 18h1.5a2 2 0 001.8-2.9c-.4-.8.2-1.6 1-1.6H18a3 3 0 003-3 9 9 0 00-9-9z"
              stroke="currentColor"
              strokeWidth="1.6"
            />
            <circle cx="7.5" cy="11" r="1.1" fill="currentColor" />
            <circle cx="9.5" cy="7" r="1.1" fill="currentColor" />
            <circle cx="14.5" cy="7" r="1.1" fill="currentColor" />
            <circle cx="16.5" cy="11" r="1.1" fill="currentColor" />
          </svg>
          Personalizar
        </button>
      </aside>

      <main className="main">
        <Outlet />
      </main>

      <PainelTema aberto={painelAberto} aoFechar={() => setPainelAberto(false)} />
    </div>
  );
}
