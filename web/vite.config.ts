// @lovable.dev/vite-tanstack-config already includes TanStack Start, React, Tailwind, tsconfig
// paths, VITE_* env injection and the @ alias. Do not add them again.
//
// EmoStream deployment: the FastAPI backend serves this app as static files from the same
// origin as the engine (/api, /ws/session). TanStack Start is therefore built in SPA mode
// (one prerendered shell, client-side routing) and the nitro server build is switched off.
// Output: dist/client (index.html, assets, build.json).
import path from "node:path";
import { defineConfig } from "@lovable.dev/vite-tanstack-config";

// In development, the dev server forwards /api and /ws to a running EmoStream backend:
//   VITE_BACKEND=https://<modal-url> npm run dev      (default http://127.0.0.1:8000)
const backend = process.env["VITE_BACKEND"] ?? "http://127.0.0.1:8000";

// Every build gets an identifier. The page carries it, the server reads it from build.json,
// and a page whose identifier differs from the server's reloads itself once.
// scripts/build_frontends.sh sets EMOSTREAM_BUILD so this app and the diagnostics client share one.
const build =
  process.env["EMOSTREAM_BUILD"] ?? new Date().toISOString().replace(/[-:T]/g, "").slice(0, 14);

// The live engine client (protocol, session, player, audio) is shared with the diagnostics
// client in ../frontend, so the wire protocol is defined in exactly one place.
const engineLib = path.resolve(__dirname, "../frontend/src/lib");

export default defineConfig({
  nitro: false,
  tanstackStart: {
    server: { entry: "server" },
    spa: { enabled: true, prerender: { outputPath: "/index.html", crawlLinks: false } },
  },
  plugins: [
    {
      name: "emostream-build-id",
      apply: "build",
      generateBundle() {
        // Client bundle only: the server bundle is used once, to prerender the shell.
        if (this.environment?.name !== "client") return;
        this.emitFile({ type: "asset", fileName: "build.json", source: JSON.stringify({ build }) });
      },
    },
  ],
  vite: {
    define: { __BUILD__: JSON.stringify(build) },
    resolve: { alias: { "@engine": engineLib } },
    server: {
      fs: { allow: [path.resolve(__dirname), engineLib] },
      proxy: {
        "/api": { target: backend, changeOrigin: true },
        "/ws": { target: backend, changeOrigin: true, ws: true },
      },
    },
  },
});
