import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { repoRoot } from "./discover";
import { extractWhatsNew, prNumbers } from "./promote";

const yml = readFileSync(join(repoRoot, ".github/workflows/promote.yml"), "utf8");

describe("promote.yml", () => {
  it("skips promotion while Pause releases is on", () => {
    expect(yml).toContain("migrate/promote.ts paused");
    const gated = yml
      .split("\n      - ")
      .filter(
        (s) =>
          s.startsWith("name: ") &&
          /(Move production|Re-run green main|What's new|Wait for|production check)/.test(s),
      );
    expect(gated.length).toBeGreaterThanOrEqual(5);
    for (const step of gated)
      expect(step, step.split("\n")[0]).toContain("steps.pause.outputs.paused != 'true'");
  });
  it("re-runs green main before moving production, then posts What's new and runs the checks", () => {
    const at = (s: string) => yml.indexOf(s);
    expect(at("Re-run green main")).toBeLessThan(at("Move production"));
    expect(at("Move production")).toBeLessThan(at("Post What's new"));
    expect(at("Post What's new")).toBeLessThan(at("Wait for Workers Builds"));
    expect(at("Wait for Workers Builds")).toBeLessThan(at("Run every production check"));
    expect(yml).toContain("refs/heads/production");
  });
});

describe("What's new lines", () => {
  it("reads the English and Bengali lines of a PR body", () => {
    const body =
      "Refs x\n\n- What's new (en): Funds now sit under Portfolio.\n- What's new (bn): ফান্ড এখন পোর্টফোলিওর নিচে।\n";
    expect(extractWhatsNew(7, body)).toEqual({
      pr: 7,
      en: "Funds now sit under Portfolio.",
      bn: "ফান্ড এখন পোর্টফোলিওর নিচে।",
    });
  });
  it("skips a PR with only one language or none", () => {
    expect(extractWhatsNew(1, "What's new (en): only english")).toBeNull();
    expect(extractWhatsNew(1, "nothing")).toBeNull();
  });
  it("finds PR numbers in squash and merge-queue subjects", () => {
    expect(prNumbers(["Add pane (#12)", "fix (#13)", "no number", "Add pane (#12)"])).toEqual([
      12, 13,
    ]);
  });
});
