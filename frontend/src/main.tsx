import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import { ThemeProvider } from "./theme/ThemeContext";
import "./index.css";

// O ThemeProvider aplica o tema (cores + título) e mantém os ajustes do
// painel de personalização. Envolve todo o app.
ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <ThemeProvider>
      <App />
    </ThemeProvider>
  </React.StrictMode>
);
