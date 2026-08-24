/**
 * Página "Explorar Grafo": desenha o inventário inteiro como um grafo
 * interativo. Nós coloridos por tipo; clicar num nó mostra os detalhes e
 * destaca os vizinhos. A LEGENDA explica qual cor é qual tipo de entidade.
 */
import { useEffect, useMemo, useState } from "react";

import { GraphData, GraphNode, explorarGrafo } from "../api";
import { GraphView, estiloDoTipo } from "../components/GraphView";
import { Theme } from "../theme/theme";
import { useTheme } from "../theme/ThemeContext";

/** Legenda: cor -> tipo de entidade (lida do tema efetivo). */
function Legenda({ tema }: { tema: Theme }) {
  const itens = Object.entries(tema.graph) as [string, { label: string; color: string }][];
  return (
    <div className="legend">
      <p className="panel-title">Legenda</p>
      {itens.map(([tipo, { label, color }]) => (
        <div className="legend-item" key={tipo}>
          <span className="legend-dot" style={{ background: color }} />
          {label}
        </div>
      ))}
    </div>
  );
}

/** Painel de detalhes do nó selecionado. */
function Detalhes({ tema, node }: { tema: Theme; node: GraphNode | null }) {
  if (!node) {
    return (
      <div className="panel-hint">
        Clique num nó para ver os detalhes e destacar os vizinhos.
      </div>
    );
  }
  const props = Object.entries(node.props ?? {}).filter(([, v]) => v !== null && v !== undefined);
  return (
    <div className="node-details">
      <p className="panel-title">{estiloDoTipo(tema, node.tipo).label}</p>
      <p className="node-name">{node.label}</p>
      {props.length > 0 && (
        <dl className="props">
          {props.map(([k, v]) => (
            <div className="prop-row" key={k}>
              <dt>{k}</dt>
              <dd>{String(v)}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

export function ExplorarGrafo() {
  const tema = useTheme();
  const [data, setData] = useState<GraphData | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [selecionado, setSelecionado] = useState<GraphNode | null>(null);

  useEffect(() => {
    explorarGrafo()
      .then(setData)
      .catch((e) => setErro(e instanceof Error ? e.message : "Falha ao carregar o grafo."));
  }, []);

  const resumo = useMemo(() => {
    if (!data) return "";
    return `${data.nodes.length} nós • ${data.edges.length} relações`;
  }, [data]);

  return (
    <div className="page-grafo">
      <h1 className="page-title">Explorar Grafo</h1>
      <p className="subtitle">
        Todo o inventário como um grafo. {resumo}
      </p>

      {erro && (
        <div className="card error">
          <strong>Não foi possível carregar o grafo.</strong>
          <p style={{ margin: "8px 0 0" }}>{erro}</p>
        </div>
      )}

      {!data && !erro && <div className="card">Carregando o grafo…</div>}

      {data && (
        <div className="grafo-layout">
          <div className="card grafo-canvas">
            <GraphView data={data} altura={620} onSelecionar={setSelecionado} />
          </div>
          <aside className="card grafo-panel">
            <Legenda tema={tema} />
            <hr className="panel-sep" />
            <Detalhes tema={tema} node={selecionado} />
          </aside>
        </div>
      )}
    </div>
  );
}
