import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Runs from the repo root so the checks in checks/C-*.test.ts sit beside the unit tests.
export default defineConfig({
  root: resolve(dirname(fileURLToPath(import.meta.url)), ".."),
  test: {
    include: [
      "api/src/**/*.test.ts",
      "api/migrate/**/*.test.ts",
      "adapters/src/**/*.test.ts",
      "tools/new-area/**/*.test.ts",
      "checks/C-*.test.ts",
    ],
    testTimeout: 30000,
  },
});
