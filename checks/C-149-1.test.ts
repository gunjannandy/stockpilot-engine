// C-149-1: new-area creates the contract file, route, schema, pane, words and a passing test, and
// the new area touches no file outside its folders and contract/.
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { repoRoot } from "../api/migrate/discover";
import { scaffold } from "../tools/new-area/scaffold";

const AREA = "zzscaffold";
const inside = (f: string) =>
  [`contract/src/${AREA}/`, `api/src/${AREA}/`, `web/src/panes/${AREA}/`, `web/src/words/${AREA}.`].some((p) =>
    f.startsWith(p),
  );

describe("C-149-1 new-area", () => {
  it("creates every piece and stays inside the area's own folders", () => {
    const root = mkdtempSync(join(tmpdir(), "area-"));
    try {
      const files = scaffold(root, AREA);
      expect(files).toEqual(
        expect.arrayContaining([
          `contract/src/${AREA}/${AREA}.ts`,
          `api/src/${AREA}/routes.ts`,
          `api/src/${AREA}/schema.ts`,
          `api/src/${AREA}/migration-map.json`,
          `api/src/${AREA}/${AREA}.test.ts`,
          `web/src/panes/${AREA}/index.tsx`,
          `web/src/words/${AREA}.en.json`,
          `web/src/words/${AREA}.bn.json`,
        ]),
      );
      expect(files.some((f) => f.includes("/migrations/") && f.endsWith(`_${AREA}.sql`))).toBe(true);
      expect(files.filter((f) => !inside(f))).toEqual([]);
      expect(() => scaffold(root, AREA)).toThrow(/taken/);
      expect(() => scaffold(root, "Bad Name")).toThrow(/lowercase/);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("adds the registry line only when asked", () => {
    const root = mkdtempSync(join(tmpdir(), "area-"));
    try {
      mkdirSync(join(root, "contract/src"), { recursive: true });
      writeFileSync(
        join(root, "contract/src/datasets.ts"),
        "export const datasets = {\n  a: { name: 'a' },\n} as const satisfies Record<string, unknown>;\n",
      );
      expect(scaffold(root, "plain")).not.toContain("contract/src/datasets.ts");
      expect(readFileSync(join(root, "contract/src/datasets.ts"), "utf8")).not.toContain("plain");
      expect(scaffold(root, "withreg", { registry: true })).toContain("contract/src/datasets.ts");
      const text = readFileSync(join(root, "contract/src/datasets.ts"), "utf8");
      expect(text).toContain('table: "withreg"');
      expect(text).toContain('import { WithregRow }');
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("makes an area whose own test passes, found by folder with no edit to app.ts", () => {
    try {
      scaffold(repoRoot, AREA);
      const out = execFileSync(
        "pnpm",
        ["exec", "vitest", "run", "--config", "api/vitest.config.ts", `api/src/${AREA}/${AREA}.test.ts`],
        { cwd: repoRoot, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
      );
      expect(out).toContain("1 passed");
    } finally {
      for (const d of [`contract/src/${AREA}`, `api/src/${AREA}`, `web/src/panes/${AREA}`])
        rmSync(join(repoRoot, d), { recursive: true, force: true });
      for (const l of ["en", "bn"]) rmSync(join(repoRoot, `web/src/words/${AREA}.${l}.json`), { force: true });
    }
  });
});
