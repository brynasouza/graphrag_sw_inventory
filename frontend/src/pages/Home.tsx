/**
 * Página "Perguntar": pergunta -> resposta. Além do texto do Claude e dos
 * fatos, mostra um MINI-GRAFO com só as entidades que foram usadas para
 * chegar naquela resposta (context.subgrafo).
 */
import { useState } from "react";

import { AskResponse, ask } from "../api";
import { Answer } from "../components/Answer";
import { AskForm } from "../components/AskForm";
import { Facts } from "../components/Facts";
import { GraphView } from "../components/GraphView";

export function Home() {
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [resposta, setResposta] = useState<AskResponse | null>(null);

  async function handleAsk(pergunta: string) {
    setLoading(true);
    setErro(null);
    setResposta(null);
    try {
      const r = await ask(pergunta);
      setResposta(r);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao consultar a API.");
    } finally {
      setLoading(false);
    }
  }

  const subgrafo = resposta?.context.subgrafo;

  return (
    <div className="container">
      <h1 className="page-title">Perguntar</h1>
      <p className="subtitle">
        Pergunte em linguagem natural sobre licenças, fornecedores e custos.
      </p>

      <AskForm onAsk={handleAsk} loading={loading} />

      {erro && (
        <div className="card error">
          <strong>Não foi possível responder.</strong>
          <p style={{ margin: "8px 0 0" }}>{erro}</p>
        </div>
      )}

      {resposta && (
        <>
          <Answer texto={resposta.answer} />

          {subgrafo && subgrafo.nodes.length > 0 && (
            <div className="card">
              <p className="mini-graph-title">
                Entidades usadas nesta resposta
              </p>
              <GraphView data={subgrafo} altura={280} interativo={false} />
            </div>
          )}

          <Facts context={resposta.context} />
        </>
      )}
    </div>
  );
}
