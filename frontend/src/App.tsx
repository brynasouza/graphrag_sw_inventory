/**
 * Componente raiz. Define as rotas do app dentro do layout com barra
 * lateral: Perguntar (/), Painel (/painel) e Explorar Grafo (/grafo).
 */
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { ExplorarGrafo } from "./pages/ExplorarGrafo";
import { Home } from "./pages/Home";
import { Painel } from "./pages/Painel";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Home />} />
          <Route path="/painel" element={<Painel />} />
          <Route path="/grafo" element={<ExplorarGrafo />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
