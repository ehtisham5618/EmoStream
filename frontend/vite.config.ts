import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development, point the app at a running backend:  VITE_BACKEND=https://<modal-url> npm run dev
const backend = process.env.VITE_BACKEND ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": { target: backend, changeOrigin: true },
      "/ws": { target: backend, changeOrigin: true, ws: true },
    },
  },
});
