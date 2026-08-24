/**
 * Mostra a resposta do Claude. Como o texto vem em Markdown (com tabelas),
 * usamos react-markdown + remark-gfm para renderizar bonito.
 */
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function Answer({ texto }: { texto: string }) {
  return (
    <div className="card answer">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{texto}</ReactMarkdown>
    </div>
  );
}
