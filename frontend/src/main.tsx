import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import { applyTheme } from "./theme/applyTheme";
import "./index.css";

// Aplica o tema (cores + título) antes de desenhar a tela.
applyTheme();

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
