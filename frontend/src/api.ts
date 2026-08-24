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

export interface AskResponse {
  answer: string;
  context: {
    pergunta: string;
    candidatos: Candidato[];
    fatos: any[];
    gastos_por_fornecedor: any[];
    subgrafo: GraphData; // mini-grafo das entidades usadas na resposta
  };
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

/** Grafo inteiro do inventário (página "Explorar Grafo"). */
export function explorarGrafo(): Promise<GraphData> {
  return getJSON<GraphData>("/graph/explore");
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

export function licencasVencendo(dias: number): Promise<Licenca[]> {
  return getJSON<Licenca[]>(`/graph/licenses?expiring_in_days=${dias}`);
}
export function gastoPorFornecedor(): Promise<GastoFornecedor[]> {
  return getJSON<GastoFornecedor[]>("/graph/costs/by-vendor");
}
export function gastoPorCentro(): Promise<GastoCentro[]> {
  return getJSON<GastoCentro[]>("/graph/costs/by-cost-center");
}
