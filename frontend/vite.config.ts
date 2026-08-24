import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Configuração do Vite (servidor de desenvolvimento + build).
// A porta 5173 é o padrão do Vite; o backend roda na 8000.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
});
