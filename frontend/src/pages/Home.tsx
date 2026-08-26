/**
 * Página "Perguntar": pergunta -> resposta. Além do texto do Claude e dos
 * fatos, mostra um MINI-GRAFO com só as entidades que foram usadas para
 * chegar naquela resposta (context.subgrafo).
 */
import { useState } from "react";

import { AskContext, Etapa, askStream } from "../api";
import { Answer } from "../components/Answer";
import { AskForm } from "../components/AskForm";
import { Etapas } from "../components/Etapas";
import { Facts } from "../components/Facts";
import { GraphView } from "../components/GraphView";
import { VerConsulta } from "../components/VerConsulta";

export function Home() {
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  // Estados do streaming: a etapa atual, o texto que cresce e o contexto (que
  // chega ANTES do texto terminar, permitindo revelar o grafo/consulta já).
  const [etapa, setEtapa] = useState<Etapa | null>(null);
  const [texto, setTexto] = useState("");
  const [contexto, setContexto] = useState<AskContext | null>(null);

  async function handleAsk(pergunta: string) {
    setLoading(true);
    setErro(null);
    setEtapa(null);
    setTexto("");
    setContexto(null);
    try {
      await askStream(pergunta, {
        onEtapa: (e) => setEtapa(e),
        onContexto: (ctx) => setContexto(ctx),
        onToken: (chunk) => setTexto((anterior) => anterior + chunk),
        onErro: (detalhe) => setErro(detalhe),
      });
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao consultar a API.");
    } finally {
      setLoading(false);
      setEtapa(null);
    }
  }

  const subgrafo = contexto?.subgrafo;

  return (
    <div className="container">
      <h1 className="page-title">Perguntar</h1>
      <p className="subtitle">
        Pergunte em linguagem natural sobre licenças, fornecedores e custos.
      </p>

      <AskForm onAsk={handleAsk} loading={loading} />

      {/* Progresso das etapas enquanto o Claude ainda não terminou de escrever. */}
      {loading && etapa && (
        <Etapas atual={etapa.etapa} resolvido={etapa.resolvido} />
      )}

      {erro && (
        <div className="card error">
          <strong>Não foi possível responder.</strong>
          <p style={{ margin: "8px 0 0" }}>{erro}</p>
        </div>
      )}

      {/* Texto em streaming (com cursor enquanto carrega). */}
      {texto && <Answer texto={texto} streaming={loading} />}

      {/* Contexto chega antes do fim do texto -> grafo e consulta já aparecem. */}
      {contexto && (
        <>
          {subgrafo && subgrafo.nodes.length > 0 && (
            <div className="card">
              <p className="mini-graph-title">
                Entidades usadas nesta resposta
              </p>
              <GraphView data={subgrafo} altura={280} interativo={false} />
            </div>
          )}

          <VerConsulta consultas={contexto.consultas} />

          <Facts context={contexto} />
        </>
      )}
    </div>
  );
}
