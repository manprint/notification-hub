/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/ingest": "http://localhost:8000",
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/setupTests.ts",
    globals: true,
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      include: ["src/**/*.{ts,tsx}"],
      // Fuori dalla misura cio' che non ha comportamento da verificare: i tipi
      // (solo dichiarazioni), il punto di ingresso della SPA, i mock dei test.
      exclude: [
        "src/main.tsx",
        "src/api/types.ts",
        "src/api/mocks/**",
        "src/setupTests.ts",
        // I test non si misurano da soli: gonfiavano il totale di dieci punti
        // e nascondevano la copertura vera del codice di produzione.
        "**/__tests__/**",
        "**/*.test.{ts,tsx}",
      ],
      // Pavimento, non obiettivo: `make fe-cov` fallisce se una modifica futura
      // scende sotto. Alzarlo quando la copertura sale, mai abbassarlo per far
      // passare una modifica.
      thresholds: {
        statements: 85,
        branches: 78,
        functions: 60,
        lines: 85,
      },
    },
  },
});
