import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

// Builds to dist/ at base "/". FastAPI serves it via app/routers/spa.py;
// the Docker image copies frontend/dist in a multi-stage build; the
// Android wrapper syncs it into assets/public via `cap sync`.
export default defineConfig({
  base: "/",
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    // "hidden": still emit .map files for server-side debugging, but
    // without the sourceMappingURL footer. Mobile pipelines delete
    // dist/**/*.map before `cap sync` (android-release.yml + the F-Droid
    // recipe) — the maps were ~2 MB of dead APK weight.
    sourcemap: "hidden",
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
