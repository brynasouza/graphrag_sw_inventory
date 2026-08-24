/**
 * Transparência: mostra os FATOS do grafo que fundamentaram a resposta.
 * Fica recolhido por padrão (o usuário abre se quiser conferir a origem).
 */
import { AskResponse } from "../api";

export function Facts({ context }: { context: AskResponse["context"] }) {
  return (
    <div className="card facts">
      <details>
        <summary>Ver os fatos do grafo usados nesta resposta</summary>

        <p style={{ marginTop: 16 }}>
          <strong>Candidatos encontrados pela busca vetorial:</strong>
        </p>
        <div>
          {context.candidatos.map((c, i) => (
            <span className="badge" key={i}>
              {c.tipo}: {c.nome} ({c.score.toFixed(3)})
            </span>
          ))}
        </div>

        <p style={{ marginTop: 16 }}>
          <strong>Dados brutos (JSON):</strong>
        </p>
        <pre>{JSON.stringify(context, null, 2)}</pre>
      </details>
    </div>
  );
}
