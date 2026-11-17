import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development, point the app at a running backend:  VITE_BACKEND=https://<modal-url> npm run dev
const backend = process.env.VITE_BACKEND ?? "http://127.0.0.1:8000";

// Every build gets an identifier. The page carries it, the server reads it from
// dist/build.json, and a page whose identifier differs from the server's reloads itself.
// scripts/build_frontends.sh sets EMOSTREAM_BUILD so this client and the product UI (web/) share one.
const build = process.env.EMOSTREAM_BUILD ?? new Date().toISOString().replace(/[-:T]/g, "").slice(0, 14);

export default defineConfig({
  // The deployed worker serves the product UI (web/) at "/" and this diagnostics client at
  // "/diagnostics/" (EMOSTREAM_BASE=/diagnostics/). Standalone builds keep "/".
  base: process.env.EMOSTREAM_BASE ?? "/",
  define: { __BUILD__: JSON.stringify(build) },
  plugins: [react(), {
    name: "emostream-build-id",
    generateBundle() {
      this.emitFile({ type: "asset", fileName: "build.json", source: JSON.stringify({ build }) });
    },
  }],
  server: {
    proxy: {
      "/api": { target: backend, changeOrigin: true },
      "/ws": { target: backend, changeOrigin: true, ws: true },
    },
  },
});
