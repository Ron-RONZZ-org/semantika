import { defineConfig } from "vitest/config";
import { svelte } from "@sveltejs/vite-plugin-svelte";

export default defineConfig({
  plugins: [svelte({ hot: false })],
  resolve: {
    conditions: ["browser"],
  },
  test: {
    environment: "happy-dom",
    include: ["src/**/*.{test,spec}.{js,ts}", "src/**/__tests__/**/*.{test,spec}.{js,ts}"],
    globals: true,
    setupFiles: ["./vitest-setup.js"],
  },
});
