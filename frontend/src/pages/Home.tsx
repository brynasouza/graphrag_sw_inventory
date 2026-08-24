/**
 * Tela principal: orquestra o estado (pergunta -> carregando -> resposta
 * ou erro) e monta os componentes.
 */
import { useState } from "react";

import { AskResponse, ask } from "../api";
import { Answer } from "../components/Answer";
import { AskForm } from "../components/AskForm";
import { Facts } from "../components/Facts";
import { Header } from "../components/Header";

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

  return (
    <div className="container">
      <Header />
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
          <Facts context={resposta.context} />
        </>
      )}
    </div>
  );
}
