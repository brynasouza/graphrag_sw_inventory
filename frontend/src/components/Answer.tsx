/**
 * Mostra a resposta do Claude. Como o texto vem em Markdown (com tabelas),
 * usamos react-markdown + remark-gfm para renderizar bonito.
 */
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function Answer({
  texto,
  streaming = false,
}: {
  texto: string;
  streaming?: boolean;
}) {
  return (
    <div className="card answer">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{texto}</ReactMarkdown>
      {/* Cursor piscando enquanto o texto ainda está chegando (streaming). */}
      {streaming && <span className="stream-cursor" aria-hidden="true" />}
    </div>
  );
}
