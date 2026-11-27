// C-064-1 concentration by stock and sector; C-065-1 the Nifty -10% shock.
import { expect, it } from "vitest";
import { concentration, niftyShock } from "../money/src/risk/risk";

const items = [
  { symbol: "AAA", sector: "Banks", value: 400, beta: 1.2 },
  { symbol: "BBB", sector: "Banks", value: 100, beta: 0.8 },
  { symbol: "CCC", sector: "IT", value: 400, beta: null },
  { symbol: "DDD", sector: null, value: 100, beta: 0.5 },
];

it("C-064-1 shares by stock and sector, with flags above the limits", () => {
  const c = concentration(items);
  expect(c.total).toBe(1000);
  expect(c.byStock.map((s) => [s.key, s.share])).toEqual([
    ["AAA", 0.4],
    ["CCC", 0.4],
    ["BBB", 0.1],
    ["DDD", 0.1],
  ]);
  expect(c.bySector.map((s) => [s.key, s.share])).toEqual([
    ["Banks", 0.5],
    ["IT", 0.4],
    ["Unknown", 0.1],
  ]);
  expect(c.flags.map((f) => `${f.kind}:${f.key}`)).toEqual([
    "sector:Banks",
    "stock:AAA",
    "stock:CCC",
    "sector:IT",
  ]);
});

it("C-065-1 each holding moves beta x the fall; no beta counts as 1", () => {
  const s = niftyShock(items);
  expect(s.lossInr).toBeCloseTo(-(400 * 0.12 + 100 * 0.08 + 400 * 0.1 + 100 * 0.05), 9);
  expect(s.lossShare).toBeCloseTo(-0.101, 9);
  expect(s.assumedBeta).toEqual(["CCC"]);
  expect(s.perStock[0]?.symbol).toBe("AAA");
});
