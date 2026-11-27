// C-069-3: lint fails any Date use in money; rounding helpers match Python's round, // and int on fixtures.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";
import { floorDiv, pyFixed, pyInt, pyProd, pyRound, pySum } from "../money/src/core/round";
import { captured } from "./captured";

/** Every use of the global `Date` in a source text: `new Date`, `Date.now`, `Date.UTC`, `globalThis.Date`, a type. */
function dateUses(text: string): string[] {
  const source = ts.createSourceFile("x.ts", text, ts.ScriptTarget.Latest, true);
  const found: string[] = [];
  const visit = (node: ts.Node) => {
    if (ts.isIdentifier(node) && node.text === "Date") {
      const parent = node.parent;
      const isMember =
        parent &&
        ts.isPropertyAccessExpression(parent) &&
        parent.name === node &&
        !isGlobalThis(parent.expression);
      const isKey =
        parent &&
        (ts.isPropertyAssignment(parent) || ts.isPropertySignature(parent)) &&
        parent.name === node;
      if (!isMember && !isKey) {
        const { line } = source.getLineAndCharacterOfPosition(node.getStart());
        found.push(`line ${line + 1}`);
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return found;
}
const isGlobalThis = (e: ts.Expression) =>
  ts.isIdentifier(e) && (e.text === "globalThis" || e.text === "window" || e.text === "self");

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) return sourceFiles(p);
    return p.endsWith(".ts") && !p.endsWith(".test.ts") ? [p] : [];
  });
}

describe("C-069-3 no Date in money", () => {
  it("the scanner catches every way of reaching Date", () => {
    expect(dateUses("const a = new Date();")).toHaveLength(1);
    expect(dateUses("const a = Date.now();")).toHaveLength(1);
    expect(dateUses("const a = Date.UTC(2026, 1, 1);")).toHaveLength(1);
    expect(dateUses("const a: Date = x;")).toHaveLength(1);
    expect(dateUses("const a = globalThis.Date.now();")).toHaveLength(1);
    expect(
      dateUses("const d = { Date: 1 }; const m = obj.Date; type T = { Date: string };"),
    ).toHaveLength(0);
    expect(dateUses("const day = '2026-01-01'; const n = toOrdinal(day);")).toHaveLength(0);
  });

  it("no source file under money/ uses Date", () => {
    const files = sourceFiles(join(__dirname, "../money/src"));
    expect(files.length).toBeGreaterThan(5);
    const bad = files.flatMap((f) => dateUses(readFileSync(f, "utf8")).map((u) => `${f}: ${u}`));
    expect(bad).toEqual([]);
  });
});

type Rounding = {
  round: [number, number, number][];
  floordiv: [number, number, number][];
  int: [number, number][];
  sum: [number[], number][];
  fixed: [number, number, string][];
};
const [fixtures] = captured<Rounding>("rounding.json") as [Rounding];

describe("C-069-3 rounding helpers match Python", () => {
  it("round(x, n) rounds half to even from the exact value", () => {
    expect(fixtures.round.length).toBeGreaterThan(1000);
    for (const [x, n, want] of fixtures.round)
      expect(pyRound(x, n), `round(${x}, ${n})`).toBe(want);
  });

  it("x // y floors the quotient", () => {
    for (const [x, y, want] of fixtures.floordiv) expect(floorDiv(x, y), `${x} // ${y}`).toBe(want);
  });

  it("int(x) truncates toward zero", () => {
    for (const [x, want] of fixtures.int) expect(pyInt(x) + 0, `int(${x})`).toBe(want + 0);
  });

  it("sum(values) adds floats the way Python 3.12 and later does", () => {
    for (const [values, want] of fixtures.sum)
      expect(pySum(values), JSON.stringify(values)).toBe(want);
  });

  it("f'{x:.nf}' formats the same text", () => {
    for (const [x, n, want] of fixtures.fixed) expect(pyFixed(x, n), `${x}:.${n}f`).toBe(want);
  });

  it("the well-known ties go to the even digit", () => {
    expect([pyRound(0.5), pyRound(1.5), pyRound(2.5), pyRound(-0.5)]).toEqual([0, 2, 2, -0]);
    expect(pyRound(2.675, 2)).toBe(2.67);
    expect(pyRound(0.0078125, 6)).toBe(0.007812);
    expect(pyProd([2, 3, 0.5])).toBe(3);
  });
});
