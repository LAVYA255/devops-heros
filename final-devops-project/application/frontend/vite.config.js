import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In local development, /api is proxied to a backend on :8000 so the browser
// never has to deal with CORS. In the container the same job is done by nginx,
// and in Kubernetes by the Ingress.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
