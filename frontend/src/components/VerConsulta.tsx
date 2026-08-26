/**
 * Painel "Ver a consulta": mostra o(s) comando(s) MongoDB REAIS por trás do
 * resultado da tela, formatados e prontos para colar no mongosh.
 *
 * Fica recolhido por padrão (segue o mesmo padrão do <Facts>). O objetivo é o
 * público técnico ver o comando por trás do resultado, não só a interface.
 */
import { useState } from "react";

import { Consulta } from "../api";

/** Um bloco de consulta com botão "Copiar" (feedback transitório "Copiado!"). */
function BlocoConsulta({ consulta }: { consulta: Consulta }) {
  const [copiado, setCopiado] = useState(false);

  async function copiar() {
    try {
      await navigator.clipboard.writeText(consulta.consulta);
      setCopiado(true);
      window.setTimeout(() => setCopiado(false), 1500);
    } catch {
      /* clipboard indisponível (ex.: sem HTTPS) — silencioso, o texto está à mostra */
    }
  }

  return (
    <div className="consulta-bloco">
      <div className="consulta-cabecalho">
        <span className="consulta-titulo">{consulta.titulo}</span>
        <button type="button" className="consulta-copiar" onClick={copiar}>
          {copiado ? "Copiado!" : "Copiar"}
        </button>
      </div>
      <pre>{consulta.consulta}</pre>
      {consulta.resultado && (
        <p className="consulta-resultado">→ {consulta.resultado}</p>
      )}
    </div>
  );
}

export function VerConsulta({ consultas }: { consultas: Consulta[] }) {
  if (!consultas || consultas.length === 0) return null;

  return (
    <div className="card consulta">
      <details>
        <summary>Ver a consulta MongoDB por trás deste resultado</summary>
        <div className="consulta-lista">
          {consultas.map((c, i) => (
            <BlocoConsulta consulta={c} key={i} />
          ))}
        </div>
      </details>
    </div>
  );
}
