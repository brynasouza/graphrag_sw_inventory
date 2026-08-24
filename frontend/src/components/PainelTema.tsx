/**
 * Painel de Personalização (drawer lateral).
 *
 * Permite trocar a identidade visual do app AO VIVO, sem recarregar e sem
 * mexer no código: nome, logo, cores, altura do logo, paleta pronta e quais
 * tipos de nó mostram rótulo sempre. Tudo é salvo no navegador (localStorage)
 * pelo ThemeContext — nunca no repositório.
 *
 * O logo enviado por upload vira um "data URL" e fica SÓ no navegador.
 */
import { ChangeEvent } from "react";

import { PresetId, TIPOS_GRAFO, TipoGrafo, presets } from "../theme/theme";
import { useCustomizacao, useTheme } from "../theme/ThemeContext";

interface Props {
  aberto: boolean;
  aoFechar: () => void;
}

export function PainelTema({ aberto, aoFechar }: Props) {
  const tema = useTheme();
  const { ajustes, atualizar, restaurar } = useCustomizacao();

  // Upload de arquivo local -> data URL (fica só no navegador).
  function aoEnviarLogo(e: ChangeEvent<HTMLInputElement>) {
    const arquivo = e.target.files?.[0];
    if (!arquivo) return;
    const leitor = new FileReader();
    leitor.onload = () => atualizar({ logo: String(leitor.result) });
    leitor.readAsDataURL(arquivo);
  }

  // Liga/desliga um tipo na lista de "rótulos sempre visíveis".
  function alternarLabel(tipo: TipoGrafo) {
    const atual = tema.labelsSempre;
    const novo = atual.includes(tipo)
      ? atual.filter((t) => t !== tipo)
      : [...atual, tipo];
    atualizar({ labelsSempre: novo });
  }

  return (
    <>
      {/* Fundo semitransparente: clicar fora fecha o painel. */}
      <div
        className={aberto ? "tema-overlay aberto" : "tema-overlay"}
        onClick={aoFechar}
        aria-hidden={!aberto}
      />

      <aside
        className={aberto ? "tema-drawer aberto" : "tema-drawer"}
        role="dialog"
        aria-label="Personalização"
        aria-hidden={!aberto}
      >
        <div className="tema-cabecalho">
          <strong>Personalização</strong>
          <button className="tema-fechar" onClick={aoFechar} aria-label="Fechar">
            ✕
          </button>
        </div>

        <div className="tema-corpo">
          {/* Nome da aplicação */}
          <label className="tema-campo">
            <span>Nome da aplicação</span>
            <input
              type="text"
              value={ajustes.brandName ?? tema.brand.name}
              onChange={(e) => atualizar({ brandName: e.target.value })}
            />
          </label>

          {/* Logo: arquivo ou URL */}
          <label className="tema-campo">
            <span>Logo (arquivo)</span>
            <input type="file" accept="image/*" onChange={aoEnviarLogo} />
          </label>
          <label className="tema-campo">
            <span>Logo (URL)</span>
            <input
              type="text"
              placeholder="https://.../logo.svg"
              value={ajustes.logo && !ajustes.logo.startsWith("data:") ? ajustes.logo : ""}
              onChange={(e) => atualizar({ logo: e.target.value })}
            />
          </label>

          {/* Altura do logo */}
          <label className="tema-campo">
            <span>Altura do logo</span>
            <input
              type="text"
              placeholder="36px"
              value={ajustes.logoHeight ?? tema.brand.logoHeight}
              onChange={(e) => atualizar({ logoHeight: e.target.value })}
            />
          </label>

          {/* Cores */}
          <div className="tema-cores">
            <label className="tema-campo">
              <span>Cor primária</span>
              <input
                type="color"
                value={tema.colors.primary}
                onChange={(e) => atualizar({ primary: e.target.value })}
              />
            </label>
            <label className="tema-campo">
              <span>Cor de destaque</span>
              <input
                type="color"
                value={tema.colors.accent}
                onChange={(e) => atualizar({ accent: e.target.value })}
              />
            </label>
          </div>

          {/* Paleta pronta */}
          <label className="tema-campo">
            <span>Paleta pronta</span>
            <select
              value={ajustes.presetId ?? "indigo"}
              onChange={(e) => atualizar({ presetId: e.target.value as PresetId })}
            >
              {(Object.keys(presets) as PresetId[]).map((id) => (
                <option key={id} value={id}>
                  {presets[id].nome}
                </option>
              ))}
            </select>
          </label>

          {/* Rótulos sempre visíveis */}
          <div className="tema-campo">
            <span>Rótulos sempre visíveis</span>
            <div className="tema-checks">
              {TIPOS_GRAFO.map((tipo) => (
                <label key={tipo} className="tema-check">
                  <input
                    type="checkbox"
                    checked={tema.labelsSempre.includes(tipo)}
                    onChange={() => alternarLabel(tipo)}
                  />
                  <span className="legend-dot" style={{ background: tema.graph[tipo].color }} />
                  {tema.graph[tipo].label}
                </label>
              ))}
            </div>
          </div>

          <button className="tema-restaurar" onClick={restaurar}>
            Restaurar padrão
          </button>
        </div>
      </aside>
    </>
  );
}
