import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server runs on :5173. The proxy forwards any request starting with
// /api to your FastAPI backend on :8000, stripping the /api prefix. This means
// the frontend calls "/api/ask" and the browser never sees a cross-origin
// request in dev -- cleaner than hardcoding http://localhost:8000 everywhere,
// and it mirrors how you'd put a reverse proxy in front of both in production.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
