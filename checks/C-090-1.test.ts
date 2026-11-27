// C-090-1: own-trading stats equal the captured Python outputs.
import { describe, expect, it } from "vitest";
import type { Day } from "../money/src/core/dates";
import { buildRecord, type Pair, Series } from "../money/src/record/record";
import { captured } from "./captured";

type Case = {
  name: string;
  input: {
    asOf: Day;
    pairs: Pair[];
    prices: Record<string, [Day, number][]>;
    nifty: [Day, number][];
  };
  output: ReturnType<typeof buildRecord>;
};

const run = (c: Case) =>
  buildRecord({
    pairs: c.input.pairs,
    asOf: c.input.asOf,
    prices: Object.fromEntries(
      Object.entries(c.input.prices).map(([s, rows]) => [s, new Series(rows)]),
    ),
    nifty: new Series(c.input.nifty),
  });

describe("C-090-1 own-trading stats equal the captured Python outputs", () => {
  const cases = captured<Case>("record.json");
  it("has captured cases", () => expect(cases.length).toBeGreaterThan(60));
  for (const c of cases) it(c.name, () => expect(run(c)).toEqual(c.output));

  it("counts only his trades and gives the two plain lines", () => {
    const hand = cases.find((c) => c.name.startsWith("hand example")) as Case;
    const got = run(hand);
    expect([got.closed, got.winners, got.losers, got.winRate]).toEqual([3, 2, 1, 66.7]);
    expect([got.avgDaysWinners, got.avgDaysLosers]).toEqual([45, 181]);
    expect(got.soldEarly).toEqual({ checked: 2, roseAfter: 1, share: 50 });
    expect(got.vsNifty).toEqual({ checked: 3, beat: 2, share: 66.7, averageGapPoints: 9.33 });
    expect(got.byMonth.map((m) => [m.month, m.gain])).toEqual([
      ["2025-02", 200],
      ["2025-03", 300],
      ["2025-07", -200],
    ]);
    expect(got.lines).toEqual([
      "Of the 3 stock trades you closed, 67% made money. Winners were held 45 days on average, losers 181.",
      "Half of the winners you sold went on to gain more within the next 3 months.",
    ]);
  });
});
