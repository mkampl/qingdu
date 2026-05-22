import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

// Build to ../app/static_v2 so FastAPI can mount it from inside the container's
// /app directory. (The Docker image copies frontend/dist via a multi-stage build —
// see Dockerfile.) Base path is /v2/ so all asset URLs resolve under that prefix.
export default defineConfig({
  base: "/v2/",
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: true,
  },
  server: {
    port: 5173,
    proxy: {
      // Proxy backend API calls to the FastAPI dev server.
      "/api": "http://localhost:8000",
      "/health": "http://localhost:8000",
      "/static": "http://localhost:8000",
    },
  },
  test: {
    environment: "happy-dom",
    globals: true,
  },
});
