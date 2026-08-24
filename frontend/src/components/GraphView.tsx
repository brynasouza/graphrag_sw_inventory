/**
 * Visualizador de grafo reutilizável (usa react-force-graph-2d).
 *
 * Os nós se organizam sozinhos por física (força). Cada nó é colorido
 * pelo seu tipo, lendo as cores de theme.ts (graph) — assim a
 * re-tematização continua em um único arquivo. Clicar num nó o seleciona
 * e DESTACA os vizinhos, escurecendo o resto.
 *
 * É usado em dois lugares:
 *   - página "Explorar Grafo" (grande, interativo, com painel de detalhes);
 *   - mini-grafo ao lado de cada resposta (menor).
 */
import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";

import { GraphData, GraphNode } from "../api";
import { theme } from "../theme/theme";

// Acesso às cores/rótulos por tipo, com um fallback seguro.
const ESTILOS = theme.graph as Record<string, { label: string; color: string }>;
export function estiloDoTipo(tipo: string) {
  return ESTILOS[tipo] ?? { label: tipo, color: theme.colors.textMuted };
}

// O id pode vir como string (antes) ou como objeto-nó (depois da física).
function idDe(v: any): string {
  return typeof v === "object" && v !== null ? v.id : v;
}

interface Props {
  data: GraphData;
  altura?: number;
  interativo?: boolean;
  onSelecionar?: (node: GraphNode | null) => void;
}

export function GraphView({ data, altura = 320, interativo = true, onSelecionar }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<any>(null);
  const [largura, setLargura] = useState(600);
  const [selId, setSelId] = useState<string | null>(null);

  // Mede a largura do container para o grafo ocupar o espaço disponível.
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const medir = () => setLargura(el.clientWidth || 600);
    medir();
    const ro = new ResizeObserver(medir);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Mapa de vizinhança (por id) para o destaque ao clicar.
  const vizinhos = useMemo(() => {
    const m = new Map<string, Set<string>>();
    for (const n of data.nodes) m.set(n.id, new Set());
    for (const e of data.edges) {
      m.get(e.source)?.add(e.target);
      m.get(e.target)?.add(e.source);
    }
    return m;
  }, [data]);

  // Dados no formato do react-force-graph ({nodes, links}). Cópia rasa para
  // não deixar a biblioteca mutar os objetos que vêm por props.
  const graphData = useMemo(
    () => ({
      nodes: data.nodes.map((n) => ({ ...n })),
      links: data.edges.map((e) => ({ ...e })),
    }),
    [data]
  );

  function ativo(id: string): boolean {
    if (!selId) return true;
    return id === selId || vizinhos.get(selId)?.has(id) === true;
  }

  function selecionar(node: any | null) {
    const id = node ? node.id : null;
    const proximo = id && id === selId ? null : id;
    setSelId(proximo);
    onSelecionar?.(proximo && node ? (node as GraphNode) : null);
  }

  if (!data.nodes.length) {
    return (
      <div className="graph-empty" style={{ height: altura }}>
        Sem dados para desenhar o grafo.
      </div>
    );
  }

  return (
    <div className="graph-wrap" ref={wrapRef} style={{ height: altura }}>
      <ForceGraph2D
        ref={fgRef}
        graphData={graphData}
        width={largura}
        height={altura}
        backgroundColor={theme.colors.surface}
        cooldownTicks={80}
        onEngineStop={() => fgRef.current?.zoomToFit(400, 30)}
        nodeRelSize={5}
        nodeLabel={(n: any) => `${estiloDoTipo(n.tipo).label}: ${n.label}`}
        onNodeClick={(n: any) => selecionar(n)}
        onBackgroundClick={() => selecionar(null)}
        linkColor={(l: any) => {
          const on = !selId || idDe(l.source) === selId || idDe(l.target) === selId;
          return on ? theme.colors.textMuted : theme.colors.border;
        }}
        linkWidth={(l: any) =>
          selId && (idDe(l.source) === selId || idDe(l.target) === selId) ? 2 : 1
        }
        linkDirectionalParticles={interativo ? 0 : 0}
        nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, escala: number) => {
          const { color } = estiloDoTipo(node.tipo);
          const on = ativo(node.id);
          const r = 5;
          ctx.globalAlpha = on ? 1 : 0.15;

          // Ponto do nó.
          ctx.beginPath();
          ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
          ctx.fillStyle = color;
          ctx.fill();
          if (node.id === selId) {
            ctx.lineWidth = 2;
            ctx.strokeStyle = theme.colors.text;
            ctx.stroke();
          }

          // Rótulo do nó (nome legível).
          const fonte = Math.max(11 / escala, 3);
          ctx.font = `${fonte}px system-ui, sans-serif`;
          ctx.textAlign = "center";
          ctx.textBaseline = "top";
          ctx.fillStyle = theme.colors.text;
          ctx.fillText(String(node.label ?? ""), node.x, node.y + r + 1);
          ctx.globalAlpha = 1;
        }}
        nodePointerAreaPaint={(node: any, cor: string, ctx: CanvasRenderingContext2D) => {
          ctx.fillStyle = cor;
          ctx.beginPath();
          ctx.arc(node.x, node.y, 6, 0, 2 * Math.PI);
          ctx.fill();
        }}
      />
    </div>
  );
}
