/**
 * Página "Painel": visão executiva usando os endpoints determinísticos
 * que já existem (sem IA). Mostra KPIs e tabelas de licenças vencendo,
 * gasto por fornecedor e gasto por centro de custo.
 */
import { useEffect, useState } from "react";

import {
  GastoCentro,
  GastoFornecedor,
  Licenca,
  gastoPorCentro,
  gastoPorFornecedor,
  licencasVencendo,
} from "../api";
import { VerConsulta } from "../components/VerConsulta";

const DIAS_VENCIMENTO = 90;

function moeda(valor: number, currency: string) {
  try {
    return new Intl.NumberFormat("pt-BR", { style: "currency", currency }).format(valor);
  } catch {
    return `${currency} ${valor.toFixed(2)}`;
  }
}

function data(iso: string) {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString("pt-BR");
}

export function Painel() {
  const [licencas, setLicencas] = useState<Licenca[]>([]);
  const [porFornecedor, setPorFornecedor] = useState<GastoFornecedor[]>([]);
  const [porCentro, setPorCentro] = useState<GastoCentro[]>([]);
  // Consultas MongoDB reais de cada card (painel "Ver a consulta").
  const [consultaLicencas, setConsultaLicencas] = useState("");
  const [consultaFornecedor, setConsultaFornecedor] = useState("");
  const [consultaCentro, setConsultaCentro] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);

  useEffect(() => {
    Promise.all([
      licencasVencendo(DIAS_VENCIMENTO),
      gastoPorFornecedor(),
      gastoPorCentro(),
    ])
      .then(([l, f, c]) => {
        setLicencas(l.dados);
        setConsultaLicencas(l.consulta);
        setPorFornecedor(f.dados);
        setConsultaFornecedor(f.consulta);
        setPorCentro(c.dados);
        setConsultaCentro(c.consulta);
      })
      .catch((e) => setErro(e instanceof Error ? e.message : "Falha ao carregar o painel."))
      .finally(() => setCarregando(false));
  }, []);

  const gastoTotal = porFornecedor.reduce((s, f) => s + f.total, 0);
  const moedaTotal = porFornecedor[0]?.currency ?? "BRL";

  if (erro) {
    return (
      <div className="container">
        <h1 className="page-title">Painel</h1>
        <div className="card error">
          <strong>Não foi possível carregar o painel.</strong>
          <p style={{ margin: "8px 0 0" }}>{erro}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-painel">
      <h1 className="page-title">Painel</h1>
      <p className="subtitle">Visão geral do inventário de software.</p>

      {carregando ? (
        <div className="card">Carregando os indicadores…</div>
      ) : (
        <>
          <div className="kpis">
            <div className="card kpi">
              <span className="kpi-num">{licencas.length}</span>
              <span className="kpi-label">Licenças vencendo em {DIAS_VENCIMENTO} dias</span>
            </div>
            <div className="card kpi">
              <span className="kpi-num">{moeda(gastoTotal, moedaTotal)}</span>
              <span className="kpi-label">Gasto total (todos os fornecedores)</span>
            </div>
            <div className="card kpi">
              <span className="kpi-num">{porFornecedor.length}</span>
              <span className="kpi-label">Fornecedores com gasto</span>
            </div>
          </div>

          <div className="card">
            <h2 className="section-title">Licenças vencendo (próximos {DIAS_VENCIMENTO} dias)</h2>
            {licencas.length === 0 ? (
              <p className="muted">Nenhuma licença vence nesse período.</p>
            ) : (
              <table className="tabela">
                <thead>
                  <tr>
                    <th>Licença</th>
                    <th>Vence em</th>
                    <th>Métrica</th>
                    <th>Custo unitário</th>
                  </tr>
                </thead>
                <tbody>
                  {licencas.map((l) => (
                    <tr key={l._id}>
                      <td>{l.name}</td>
                      <td>{data(l.expires_at)}</td>
                      <td>{l.metric}</td>
                      <td>{moeda(l.unit_cost, l.currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <VerConsulta
              consultas={[
                { titulo: "Licenças vencendo (find)", consulta: consultaLicencas },
              ]}
            />
          </div>

          <div className="painel-duplo">
            <div className="card">
              <h2 className="section-title">Gasto por fornecedor</h2>
              <table className="tabela">
                <thead>
                  <tr>
                    <th>Fornecedor</th>
                    <th>Total</th>
                  </tr>
                </thead>
                <tbody>
                  {porFornecedor.map((f) => (
                    <tr key={f.vendor}>
                      <td>{f.vendor}</td>
                      <td>{moeda(f.total, f.currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <VerConsulta
                consultas={[
                  { titulo: "Gasto por fornecedor (aggregate)", consulta: consultaFornecedor },
                ]}
              />
            </div>

            <div className="card">
              <h2 className="section-title">Gasto por centro de custo</h2>
              <table className="tabela">
                <thead>
                  <tr>
                    <th>Centro</th>
                    <th>Nome</th>
                    <th>Total</th>
                  </tr>
                </thead>
                <tbody>
                  {porCentro.map((c) => (
                    <tr key={c.cost_center}>
                      <td>{c.cost_center}</td>
                      <td>{c.cost_center_name}</td>
                      <td>{moeda(c.total, c.currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <VerConsulta
                consultas={[
                  { titulo: "Gasto por centro de custo (aggregate)", consulta: consultaCentro },
                ]}
              />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
