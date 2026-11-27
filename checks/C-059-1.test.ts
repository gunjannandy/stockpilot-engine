// C-059-1: lots from trades and corporate actions equal the captured Python outputs.
import { describe, expect, it } from "vitest";
import { dedupeTrades, holdings, rebuild } from "../money/src/lots/rebuild";
import type { Action, KiteSnapshot, RebuildResult, Trade } from "../money/src/lots/types";
import { canonical, captured } from "./captured";

type Case = {
  name: string;
  input: {
    trades: Trade[];
    actions: Action[];
    stocks: Record<string, string>;
    kite: KiteSnapshot | null;
  };
  output: RebuildResult & { saved: number; holdings: unknown[] };
};
const cases = captured<Case>("lots.json");

describe("C-059-1 lots equal the captured Python outputs", () => {
  it("has captured cases", () => {
    expect(cases.length).toBeGreaterThan(100);
  });

  for (const c of cases) {
    it(c.name, () => {
      const trades = dedupeTrades(c.input.trades);
      expect(trades.length).toBe(c.output.saved);
      const got = rebuild({ ...c.input, trades });
      expect(canonical(got.lots)).toEqual(canonical(c.output.lots));
      expect(canonical(got.sales)).toEqual(canonical(c.output.sales));
      expect(got.unmatchedSells).toEqual(c.output.unmatchedSells);
      const hasDemerger = c.input.actions.some((a) => a.kind === "demerger");
      if (!hasDemerger) expect(got.lots).toEqual(c.output.lots);
      expect(canonical(holdings(got.lots))).toEqual(canonical(c.output.holdings));
    });
  }
});
