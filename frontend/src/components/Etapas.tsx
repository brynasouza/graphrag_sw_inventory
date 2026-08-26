/**
 * Indicador de progresso das etapas do GraphRAG:
 *   buscando entidade → percorrendo grafo → redigindo.
 *
 * Numa demo, ver o sistema trabalhando é melhor que uma tela parada — e
 * reforça a narrativa das duas fases (busca semântica + travessia do grafo).
 * Cores vêm todas do tema (var(--color-*)); nada fixo aqui.
 */
const PASSOS: { chave: string; label: string }[] = [
  { chave: "buscando", label: "Buscando entidade" },
  { chave: "percorrendo", label: "Percorrendo grafo" },
  { chave: "redigindo", label: "Redigindo resposta" },
];

interface Props {
  atual: string; // chave da etapa em andamento
  resolvido?: string; // o que o $vectorSearch resolveu (mostrado ao percorrer)
}

export function Etapas({ atual, resolvido }: Props) {
  const idx = PASSOS.findIndex((p) => p.chave === atual);

  return (
    <div className="card etapas-card">
      <div className="etapas">
        {PASSOS.map((p, i) => {
          const estado =
            i < idx ? " etapa-feita" : i === idx ? " etapa-ativa" : "";
          return (
            <div className={"etapa" + estado} key={p.chave}>
              <span className="etapa-bolinha" />
              <span className="etapa-label">{p.label}</span>
              {i < PASSOS.length - 1 && <span className="etapa-trilho" />}
            </div>
          );
        })}
      </div>
      {resolvido && <p className="etapa-resolvido">→ {resolvido}</p>}
    </div>
  );
}
