import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev (`npm run dev` on :5173) we proxy REST + WebSocket to the FastAPI backend
// on :8800 (the port run.ps1/run.sh start uvicorn on). In production the backend
// serves the built files from web/dist (same origin), so no proxy is needed.
const BACKEND = process.env.BACKEND_URL || "http://localhost:8800";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: BACKEND,
        changeOrigin: true,
        ws: true,
      },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        // Split heavy vendors into their own chunks so the main bundle stays small
        // and these load/cache independently.
        manualChunks: {
          react: ["react", "react-dom"],
          markdown: ["react-markdown", "remark-gfm"],
          highlight: ["highlight.js/lib/common"],
        },
      },
    },
  },
});
