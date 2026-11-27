// C-164-1: every colour, type size and spacing comes from the one token file; a hard-coded colour fails lint.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { repoRoot } from "../api/migrate/discover";

const TOKENS = "web/src/theme/tokens.css";
const COLOUR = /#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|oklch|oklab|lab|lch)\(/;
const FONT_PX = /font-size:\s*[\d.]+px/;

function files(dir: string): string[] {
  return readdirSync(join(repoRoot, dir)).flatMap((n) => {
    const rel = `${dir}/${n}`;
    if (statSync(join(repoRoot, rel)).isDirectory()) return files(rel);
    return /\.(css|tsx?)$/.test(n) && !/\.test\.tsx?$/.test(n) ? [rel] : [];
  });
}
const offenders = (re: RegExp) =>
  files("web/src")
    .filter((f) => f !== TOKENS)
    .filter((f) =>
      readFileSync(join(repoRoot, f), "utf8")
        .split("\n")
        .some((l) => re.test(l)),
    );

describe("C-164-1 one token file", () => {
  it("no hard-coded colour outside the token file", () => {
    expect(offenders(COLOUR)).toEqual([]);
  });
  it("no pixel font size outside the token file (text scales with the size switch)", () => {
    expect(offenders(FONT_PX)).toEqual([]);
  });
  it("the token file defines light, dark and the size steps", () => {
    const t = readFileSync(join(repoRoot, TOKENS), "utf8");
    for (const s of [
      ':root[data-theme="dark"]',
      'html[data-size="large"]',
      "--primary:",
      "--fs-body:",
    ])
      expect(t).toContain(s);
  });
});
