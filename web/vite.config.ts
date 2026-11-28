import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
import { serviceWorker } from "./sw-plugin";

export default defineConfig({
  plugins: [react(), serviceWorker()],
  server: { proxy: { "/api": "http://localhost:8787" } },
  test: { environment: "jsdom", globals: false, include: ["src/**/*.test.{ts,tsx}"] },
});
