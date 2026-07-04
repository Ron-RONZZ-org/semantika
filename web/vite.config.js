import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

export default defineConfig({
  plugins: [svelte()],
  server: {
    port: 5173,
    proxy: {
      // Defaults to 8001; override via SEMANTIKA_PORT env var when backend
      // runs on a different port (e.g. after port conflict or --port 0):
      //   SEMANTIKA_PORT=8765 npm run dev
      "/api": `http://127.0.0.1:${process.env.SEMANTIKA_PORT || 8001}`,
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
