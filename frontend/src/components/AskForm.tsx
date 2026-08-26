/**
 * Formulário de pergunta: caixa de texto + botão, com sugestões prontas.
 *
 * As três primeiras são SEMÂNTICAS de propósito: o termo ("virtualização",
 * "contêineres", "colaboração/documentação") não existe em nenhum campo do
 * banco — só a busca vetorial as resolve para a entidade certa (um find() por
 * palavra-chave devolveria vazio). A última exercita a travessia $lookup
 * (impacto), para a demo mostrar as duas etapas do GraphRAG.
 */
import { FormEvent, useState } from "react";

const EXEMPLOS = [
  "Quanto custa nossa virtualização?",
  "O que temos de plataforma de contêineres?",
  "Nossos gastos com colaboração e documentação",
  "Se a licença vSphere Standard 2026 expirar, quais times são impactados?",
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
