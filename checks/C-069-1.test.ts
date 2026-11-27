// C-069-1: every Python money test case runs against the TypeScript and matches.
// The Python money modules are deleted only after the private run (C-069-2) has matched them on the
// vault's real rows; until then this check proves the port against everything the tests captured.
import { describe, expect, it } from "vitest";
import { compareDays, type Day } from "../money/src/core/dates";
import { mark } from "../money/src/record/acted";
import { buildRecord, type Pair, Series } from "../money/src/record/record";
import { type HeldInput, held, withoutDust } from "../money/src/units/positions";
import { findings, gaps } from "../money/src/units/units";
import { canonical, captured } from "./captured";

type PositionsCase = {
  name: string;
  asOf: Day;
  input: Omit<HeldInput, "asOf" | "rate" | "rateOn" | "turnsLongTermOn" | "unitPrices"> & {
    fx: [Day, number][];
    lotsById: HeldInput["lots"];
    turnsLongTermOn: {
      kind: string;
      isin: string | null;
      currency: string | null;
      acquiredOn: Day;
      day: Day | null;
    }[];
    prices: Record<string, number | null>;
  };
  output: { positions: unknown[]; gaps: unknown[]; findings: unknown[] };
};

function worldOf(c: PositionsCase): HeldInput {
  const fx = c.input.fx;
  const rateOn = (day: Day): number | null => {
    let rate: number | null = null;
    for (const [d, r] of fx) if (compareDays(d, day) <= 0) rate = r;
    return rate;
  };
  const rule = new Map(
    c.input.turnsLongTermOn.map((r) => [
      `${r.kind}|${r.isin}|${r.currency}|${r.acquiredOn}`,
      r.day,
    ]),
  );
  return {
    ...c.input,
    asOf: c.asOf,
    rate: rateOn(c.asOf),
    rateOn,
    turnsLongTermOn: (q) => {
      const k = `${q.kind}|${q.isin}|${q.currency}|${q.acquiredOn}`;
      if (!rule.has(k)) throw new Error(`no captured long-term day for ${k}`);
      return rule.get(k) ?? null;
    },
    unitPrices: (items) =>
      items.map((i) => {
        const k = `${i.kind}|${i.symbol}|${i.isin}`;
        if (!(k in c.input.prices)) throw new Error(`no captured price for ${k}`);
        return c.input.prices[k] ?? null;
      }),
  };
}

describe("C-069-1 positions and the unit check match the Python", () => {
  const cases = captured<PositionsCase>("positions.json");
  it("has captured cases", () => expect(cases.length).toBeGreaterThan(90));
  for (const c of cases) {
    it(c.name, () => {
      const got = held(worldOf(c));
      expect(got.map((p) => ({ ...p, value: undefined }))).toEqual(
        (c.output.positions as Record<string, unknown>[]).map((p) => ({ ...p, value: undefined })),
      );
      const g = gaps({ lots: c.input.lotsById, kite: c.input.kite, stocks: c.input.stocks });
      expect(canonical(g)).toEqual(canonical(c.output.gaps));
      expect(findings(g)).toEqual(c.output.findings);
    });
  }
});

describe("C-069-1 the dust line matches the Python", () => {
  type Dust = {
    input: {
      symbol: string;
      quantity: number;
      avgCost: number | null;
      price: number | null;
      source: string;
    }[];
    output: string[];
  };
  for (const [n, c] of captured<Dust>("dust.json").entries()) {
    it(`dust case ${n}`, () => {
      const rows = c.input.map((r) => ({
        kind: "equity",
        symbol: r.symbol,
        isin: null,
        name: r.symbol,
        quantity: r.quantity,
        avgCost: r.avgCost,
        price: r.price,
        source: r.source,
        lots: [],
        check: null,
      }));
      expect(withoutDust(rows).map((p) => p.symbol)).toEqual(c.output);
    });
  }
});

describe("C-069-1 the own record matches the Python", () => {
  type RecordCase = {
    name: string;
    input: {
      asOf: Day;
      pairs: Pair[];
      prices: Record<string, [Day, number][]>;
      nifty: [Day, number][];
    };
    output: unknown;
  };
  const cases = captured<RecordCase>("record.json");
  for (const c of cases) {
    it(c.name, () => {
      const prices = Object.fromEntries(
        Object.entries(c.input.prices).map(([s, rows]) => [s, new Series(rows)]),
      );
      expect(
        buildRecord({
          pairs: c.input.pairs,
          asOf: c.input.asOf,
          prices,
          nifty: new Series(c.input.nifty),
        }),
      ).toEqual(c.output);
    });
  }
});

describe("C-069-1 the acted-on marking matches the Python", () => {
  type ActedCase = {
    input: {
      openCalls: { id: number; symbol: string; madeOn: Day; kind: string | null }[];
      confirmedTrades: { symbol: string; side: string; tradeDate: Day }[];
      kiteSyncs: Record<string, unknown>[][];
      holidays: Day[];
    };
    output: { marked: number; actedOn: [number, Day][] };
  };
  for (const [n, c] of captured<ActedCase>("acted.json").entries()) {
    it(`acted case ${n}`, async () => {
      const { kiteTrades } = await import("../money/src/record/acted");
      const got = mark({
        openCalls: c.input.openCalls,
        confirmedTrades: c.input.confirmedTrades,
        kite: kiteTrades(c.input.kiteSyncs),
        holidays: new Set(c.input.holidays),
      });
      expect(got.length).toBe(c.output.marked);
      expect(got.map((m) => [m.id, m.actedOn])).toEqual(c.output.actedOn);
    });
  }
});
