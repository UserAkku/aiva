import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

// In dev (`npm run dev`, port 5173) the API and the device WebSocket are proxied to
// the Python server on :8000. In production FastAPI serves the built files itself.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", ws: true },
      "/xiaozhi": { target: "http://localhost:8000", ws: true },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    chunkSizeWarningLimit: 900,
    // the AudioWorklet must be a real file (Safari rejects data: URLs in addModule)
    assetsInlineLimit: (file) => (file.endsWith(".js") ? false : undefined),
  },
});
