import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

const disableWatch = process.env.DISABLE_WATCH === "true";

export default defineConfig({
  plugins: [svelte()],
  server: {
    port: 6016,
    watch: disableWatch ? null : undefined,
    hmr: disableWatch ? false : undefined,
    proxy: {
      // Defaults to 6015; override via SEMANTIKA_PORT env var when backend
      // runs on a different port (e.g. after port conflict or --port 0):
      //   SEMANTIKA_PORT=8765 npm run dev
      "/api": `http://127.0.0.1:${process.env.SEMANTIKA_PORT || 6015}`,
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
