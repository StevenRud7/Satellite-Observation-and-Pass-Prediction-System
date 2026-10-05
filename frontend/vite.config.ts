/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
  build: {
    rollupOptions: {
      output: {
        // three.js is only needed for the (lazy-loaded) 3D globe tab;
        // splitting it out keeps the main bundle from paying for it
        // upfront. Deeper bundle-size work belongs to Phase 10.
        manualChunks: {
          three: ["three"],
          recharts: ["recharts"],
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/setupTests.ts"],
  },
});
