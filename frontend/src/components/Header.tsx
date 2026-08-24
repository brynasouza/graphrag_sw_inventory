/**
 * Cabeçalho: logo + nome da marca, vindos do theme.ts.
 */
import { theme } from "../theme/theme";

export function Header() {
  return (
    <>
      <div className="header">
        <img src={theme.brand.logo} alt={theme.brand.name} />
        <h1>{theme.brand.name}</h1>
      </div>
      <p className="subtitle">
        Pergunte em linguagem natural sobre licenças, fornecedores e custos.
      </p>
    </>
  );
}
