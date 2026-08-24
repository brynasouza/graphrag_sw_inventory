/**
 * Comunicação com o backend (API FastAPI).
 *
 * Uma única função `ask`: manda a pergunta para POST /ask e devolve a
 * resposta + os fatos do grafo. A URL vem de VITE_API_URL (.env) ou cai
 * no padrão local http://localhost:8000.
 */

const API_URL =
  (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

// --- Formato da resposta do /ask (espelha o backend) ---
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
  };
}

export async function ask(question: string): Promise<AskResponse> {
  const res = await fetch(`${API_URL}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });

  if (!res.ok) {
    // Tenta ler a mensagem de erro amigável que o backend manda (detail).
    let detalhe = `Erro ${res.status}`;
    try {
      const j = await res.json();
      if (j?.detail) detalhe = j.detail;
    } catch {
      /* ignora corpo não-JSON */
    }
    throw new Error(detalhe);
  }

  return res.json();
}
