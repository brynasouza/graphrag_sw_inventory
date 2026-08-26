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
