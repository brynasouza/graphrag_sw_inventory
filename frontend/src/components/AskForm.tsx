/**
 * Formulário de pergunta: caixa de texto + botão, com sugestões prontas
 * (as 3 perguntas-alvo do projeto).
 */
import { FormEvent, useState } from "react";

const EXEMPLOS = [
  "Quais projetos usam a licença da VMware e quando ela expira?",
  "Se a licença vSphere Standard 2026 expirar, quais times são impactados?",
  "Quanto gastamos com a VMware por centro de custo?",
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
