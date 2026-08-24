/**
 * Contexto de tema (React).
 *
 * Guarda os AJUSTES feitos no painel de personalização, calcula o TEMA
 * EFETIVO (padrão do theme.ts + ajustes) e o disponibiliza para todo o app:
 *
 *   - useTheme()        -> o tema efetivo, para DESENHAR (cores, rótulos...).
 *   - useCustomizacao() -> ler/alterar os ajustes, para o PAINEL.
 *
 * Sempre que o tema muda, reaplicamos as variáveis CSS e persistimos os
 * ajustes no navegador (localStorage). Assim a mudança aparece na hora e
 * sobrevive ao recarregar a página.
 */
import { ReactNode, createContext, useContext, useLayoutEffect, useMemo, useState } from "react";

import { Theme } from "./theme";
import { aplicarVars } from "./applyTheme";
import { Ajustes, carregar, limpar, salvar, temaEfetivo } from "./temaRuntime";

interface ValorContexto {
  tema: Theme;
  ajustes: Ajustes;
  atualizar: (patch: Partial<Ajustes>) => void;
  restaurar: () => void;
}

const ThemeContext = createContext<ValorContexto | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  // Começa com o que estiver salvo no navegador (ou {} = padrão).
  const [ajustes, setAjustes] = useState<Ajustes>(() => carregar());

  const tema = useMemo(() => temaEfetivo(ajustes), [ajustes]);

  // Aplica as variáveis CSS ANTES de pintar a tela (evita "piscar").
  useLayoutEffect(() => {
    aplicarVars(tema);
  }, [tema]);

  const valor = useMemo<ValorContexto>(
    () => ({
      tema,
      ajustes,
      atualizar(patch) {
        setAjustes((atual) => {
          const proximo = { ...atual, ...patch };
          salvar(proximo);
          return proximo;
        });
      },
      restaurar() {
        limpar();
        setAjustes({});
      },
    }),
    [tema, ajustes]
  );

  return <ThemeContext.Provider value={valor}>{children}</ThemeContext.Provider>;
}

function usarContexto(): ValorContexto {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useTheme/useCustomizacao precisam estar dentro de <ThemeProvider>.");
  }
  return ctx;
}

/** O tema efetivo, para os componentes desenharem. */
export function useTheme(): Theme {
  return usarContexto().tema;
}

/** Ajustes atuais + funções para o painel de personalização. */
export function useCustomizacao() {
  const { ajustes, atualizar, restaurar } = usarContexto();
  return { ajustes, atualizar, restaurar };
}
