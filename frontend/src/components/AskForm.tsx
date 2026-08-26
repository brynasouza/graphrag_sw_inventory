/**
 * Formulário de pergunta: caixa de texto + botão, com sugestões prontas.
 *
 * As três primeiras são SEMÂNTICAS de propósito: o termo ("virtualização",
 * "contêineres", "colaboração/documentação") não existe em nenhum campo do
 * banco — só a busca vetorial as resolve para a entidade certa (um find() por
 * palavra-chave devolveria vazio). A quarta exercita a travessia $lookup
 * (impacto), para a demo mostrar as duas etapas do GraphRAG.
 *
 * A última é a PROVA DE QUE NÃO ALUCINA: a Salesforce não existe no inventário.
 * O sistema deve dizer que não tem o dado — em vez de inventar um número —,
 * evidenciando o "grounding" (o grafo garante os fatos; o LLM não estima).
 *
 * Se mudar esta lista, atualize também PERGUNTAS_DEMO em
 * backend/app/retrieval/demo_cache.py (elas se espelham para o cache da demo).
 */
import { FormEvent, useState } from "react";

const EXEMPLOS = [
  "Quanto custa nossa virtualização?",
  "O que temos de plataforma de contêineres?",
  "Nossos gastos com colaboração e documentação",
  "Se a licença vSphere Standard 2026 expirar, quais times são impactados?",
  "Quanto gastamos com a Salesforce?",
];

interface Props {
  onAsk: (pergunta: string) => void;
  loading: boolean;
}

export function AskForm({ onAsk, loading }: Props) {
  const [texto, setTexto] = useState("");

  function enviar(e: FormEvent) {
    e.preventDefault();
    const p = texto.trim();
    if (p) onAsk(p);
  }

  return (
    <div className="card">
      <form className="ask-form" onSubmit={enviar}>
        <input
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          placeholder="Ex.: Quanto gastamos com a VMware por centro de custo?"
          disabled={loading}
        />
        <button type="submit" disabled={loading}>
          {loading ? "Pensando…" : "Perguntar"}
        </button>
      </form>

      <div className="examples">
        {EXEMPLOS.map((ex) => (
          <button
            key={ex}
            type="button"
            disabled={loading}
            onClick={() => {
              setTexto(ex);
              onAsk(ex);
            }}
          >
            {ex}
          </button>
        ))}
      </div>
    </div>
  );
}
