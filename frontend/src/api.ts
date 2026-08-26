/**
 * Comunicação com o backend (API FastAPI).
 *
 * A URL vem de VITE_API_URL (.env) ou cai no padrão local
 * http://localhost:8000. Todas as funções tratam erro do mesmo jeito:
 * leem a mensagem amigável (`detail`) que o backend manda.
 */

const API_URL =
  (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

/** Lê a mensagem de erro amigável (detail) do backend, se houver. */
async function erroDe(res: Response): Promise<Error> {
  let detalhe = `Erro ${res.status}`;
  try {
    const j = await res.json();
    if (j?.detail) detalhe = j.detail;
  } catch {
    /* ignora corpo não-JSON */
  }
  return new Error(detalhe);
}

/** GET genérico que devolve JSON tipado. */
async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`);
  if (!res.ok) throw await erroDe(res);
  return res.json();
}

// --- Grafo (nós + arestas), no formato canônico do backend ---
export interface GraphNode {
  id: string;
  tipo: string;
  label: string;
  props: Record<string, any>;
}
export interface GraphEdge {
  source: string;
  target: string;
  tipo: string;
  label: string | null;
}
export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

// --- Resposta do /ask (espelha o backend) ---
export interface Candidato {
  tipo: string;
  nome: string;
  score: number;
}

// Um comando MongoDB real por trás do resultado (painel "Ver a consulta").
export interface Consulta {
  titulo: string;
  consulta: string;
  // Opcional: para o $vectorSearch, as entidades reais que a busca resolveu
  // (nome, tipo e score) — evidencia a etapa semântica antes do $lookup.
  resultado?: string;
}

export interface AskResponse {
  answer: string;
  context: {
    pergunta: string;
    candidatos: Candidato[];
    fatos: any[];
    gastos_por_fornecedor: any[];
    subgrafo: GraphData; // mini-grafo das entidades usadas na resposta
    consultas: Consulta[]; // comandos MongoDB que rodaram nesta resposta
  };
}

// Envelope dos GETs quando pedimos a consulta junto (?incluir_consulta=true).
export interface ComConsulta<T> {
  dados: T;
  consulta: string;
}

export async function ask(question: string): Promise<AskResponse> {
  const res = await fetch(`${API_URL}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) throw await erroDe(res);
  return res.json();
}

// --- Versão em STREAMING (SSE) do /ask ---
// O contexto (subgrafo, consultas, fatos…) é o mesmo do /ask; só chega antes,
// via evento "contexto", enquanto o texto ainda está sendo escrito.
export type AskContext = AskResponse["context"];

// Uma etapa do processamento (para mostrar o progresso na tela).
export interface Etapa {
  etapa: "buscando" | "percorrendo" | "redigindo";
  label: string;
  resolvido?: string; // o que o $vectorSearch resolveu (só na etapa "percorrendo")
}

export interface AskStreamHandlers {
  onEtapa?: (etapa: Etapa) => void;
  onContexto?: (ctx: AskContext) => void;
  onToken?: (chunk: string) => void;
  onFim?: (tempos: Record<string, number>) => void;
  onErro?: (detail: string) => void;
}

/** Processa um frame SSE ("event: X\n data: {...}") e chama o handler certo. */
function processarFrameSSE(frame: string, h: AskStreamHandlers): void {
  let evento = "message";
  const linhasData: string[] = [];
  for (const linha of frame.split("\n")) {
    if (linha.startsWith("event:")) evento = linha.slice(6).trim();
    else if (linha.startsWith("data:")) linhasData.push(linha.slice(5).replace(/^ /, ""));
  }
  if (linhasData.length === 0) return;
  const dados = JSON.parse(linhasData.join("\n"));
  switch (evento) {
    case "etapa":
      h.onEtapa?.(dados as Etapa);
      break;
    case "contexto":
      h.onContexto?.(dados as AskContext);
      break;
    case "token":
      h.onToken?.((dados as { t: string }).t);
      break;
    case "fim":
      h.onFim?.((dados as { tempos: Record<string, number> }).tempos);
      break;
    case "erro":
      h.onErro?.((dados as { detail: string }).detail);
      break;
  }
}

/**
 * Faz a pergunta ao /ask/stream e chama os handlers conforme os eventos SSE
 * chegam. Usa fetch + ReadableStream (o EventSource nativo só faz GET, e aqui
 * é POST com corpo JSON).
 */
export async function askStream(
  question: string,
  handlers: AskStreamHandlers
): Promise<void> {
  const res = await fetch(`${API_URL}/ask/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!res.ok || !res.body) throw await erroDe(res);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // Frames SSE são separados por linha em branco (\n\n).
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      if (frame.trim()) processarFrameSSE(frame, handlers);
    }
  }
}

/** Grafo inteiro do inventário + a consulta real (página "Explorar Grafo"). */
export function explorarGrafo(): Promise<ComConsulta<GraphData>> {
  return getJSON<ComConsulta<GraphData>>("/graph/explore?incluir_consulta=true");
}

// --- Dados do Painel (reusam endpoints determinísticos já existentes) ---
export interface Licenca {
  _id: string;
  name: string;
  expires_at: string;
  unit_cost: number;
  currency: string;
  metric: string;
}
export interface GastoFornecedor {
  vendor: string;
  total: number;
  currency: string;
}
export interface GastoCentro {
  cost_center: string;
  cost_center_name: string;
  total: number;
  currency: string;
}

export function licencasVencendo(dias: number): Promise<ComConsulta<Licenca[]>> {
  return getJSON<ComConsulta<Licenca[]>>(
    `/graph/licenses?expiring_in_days=${dias}&incluir_consulta=true`
  );
}
export function gastoPorFornecedor(): Promise<ComConsulta<GastoFornecedor[]>> {
  return getJSON<ComConsulta<GastoFornecedor[]>>(
    "/graph/costs/by-vendor?incluir_consulta=true"
  );
}
export function gastoPorCentro(): Promise<ComConsulta<GastoCentro[]>> {
  return getJSON<ComConsulta<GastoCentro[]>>(
    "/graph/costs/by-cost-center?incluir_consulta=true"
  );
}
