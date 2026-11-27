// C-059-3: dust holdings never become positions.
import { describe, expect, it } from "vitest";
import { DUST_INR, type Position, positionValue, withoutDust } from "../money/src/units/positions";

const pos = (
  symbol: string,
  quantity: number,
  price: number | null,
  source = "statement",
): Position => ({
  kind: "equity",
  symbol,
  isin: null,
  name: symbol,
  quantity,
  avgCost: null,
  price,
  source,
  lots: [],
  check: null,
});

describe("C-059-3 dust holdings never become positions", () => {
  it("drops a statement-only leftover under the dust line and keeps the rest", () => {
    const kept = withoutDust([
      pos("BIG", 10, 500.0),
      pos("DUST", 0.195, 1000.0),
      pos("EDGE", 1, DUST_INR),
    ]);
    expect(kept.map((p) => p.symbol)).toEqual(["BIG", "EDGE"]);
  });

  it("keeps a small holding Kite or a document shows", () => {
    const kept = withoutDust([pos("TINY", 1, 200.0, "kite"), pos("DOCS", 1, 300.0, "lots")]);
    expect(kept.map((p) => p.symbol)).toEqual(["TINY", "DOCS"]);
  });

  it("keeps a holding with no price, so a gap never hides it", () => {
    expect(withoutDust([pos("NOPRICE", 5, null)]).map((p) => p.symbol)).toEqual(["NOPRICE"]);
  });

  it("values a unit at its price, else its average cost, else nothing", () => {
    expect(positionValue(pos("A", 2, 10))).toBe(20);
    expect(positionValue({ ...pos("B", 2, null), avgCost: 7 })).toBe(14);
    expect(positionValue(pos("C", 2, null))).toBe(0);
  });
});
