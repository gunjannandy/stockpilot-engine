// C-137-1: lane branches start no build; each preview branch gets its own address on the preview D1.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { shouldBuild } from "../api/migrate/build";
import { repoRoot } from "../api/migrate/discover";

const read = (f: string) => readFileSync(join(repoRoot, f), "utf8");
const dbId = (t: string) => /database_id\s*=\s*"([^"]+)"/.exec(t)?.[1];

describe("C-137-1 previews", () => {
  it("builds only production and preview branches; a lane branch builds nothing", () => {
    expect(shouldBuild("lane/SKELAPI")).toBe(false);
    expect(shouldBuild("main")).toBe(false);
    expect(shouldBuild("production")).toBe(true);
    expect(shouldBuild("preview/today")).toBe(true);
  });
  it("starts no GitHub workflow for lane or preview branches", () => {
    for (const f of ["ci.yml", "promote.yml"]) {
      const t = read(`.github/workflows/${f}`);
      expect(t, f).not.toMatch(/lane\/|preview\//);
    }
  });
  it("gives previews their own address on the preview Worker and the preview D1", () => {
    const prod = read("wrangler.toml");
    const prev = read("wrangler.preview.toml");
    expect(prev).toMatch(/^name = "stockpilot-preview"/m);
    expect(prev).toMatch(/^preview_urls = true/m);
    expect(prev).toMatch(/binding = "DB"/);
    expect(prod).toMatch(/^name = "stockpilot-app"/m);
    expect(dbId(prev)).toBeTruthy();
    expect(dbId(prev)).not.toBe(dbId(prod));
    expect(prev).toContain("stockpilot-v3-preview");
  });
});
