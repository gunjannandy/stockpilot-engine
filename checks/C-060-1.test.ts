// C-060-1: tax equals the captured Python outputs.
import { describe, expect, it } from "vitest";
import {
  fyLabel,
  fyOf,
  grandfatheredCost,
  harvest,
  incomeTax,
  inputs,
  mfBucket,
  netGains,
  openLots,
  type RateOn,
  realise,
  rulesFor,
  scheduleFa,
  slabTax,
  type TaxLot,
  type TaxRules,
  type TaxSale,
  term,
  turnsLongTermOn,
} from "../money/src/tax/tax";
import { canonical, captured } from "./captured";

type Out<T> = { ok: T } | { error: string };
// biome-ignore lint/suspicious/noExplicitAny: captured JSON is checked by the comparisons themselves
type Any = any;
const [c] = captured<Any>("tax.json");

const rateOf =
  (table: Record<string, number>): RateOn =>
  (day) => {
    const ks = Object.keys(table).filter((k) => k <= day);
    return ks.length ? table[ks.sort().pop() as string] : null;
  };
const same = (got: unknown, want: unknown) => expect(canonical([got])).toEqual(canonical([want]));
const unInf = (r: Any): TaxRules => ({
  ...r,
  slabs: r.slabs.map(([u, x]: [number | string, number]) => [u === "inf" ? null : u, x]),
});
const check = <T>(want: Out<T>, run: () => unknown) => {
  if ("error" in want) {
    try {
      run();
    } catch (e) {
      expect((e as Error).name === want.error || want.error === "ValueError").toBe(true);
      return;
    }
    throw new Error(`expected ${want.error}`);
  }
  same(run(), want.ok);
};
const rules26 = rulesFor(2026);

describe("C-060-1 tax equals the captured Python outputs", () => {
  it("has captured cases", () => {
    expect(c.income_tax.length).toBeGreaterThan(50);
    expect(c.realise.length).toBeGreaterThan(50);
  });
  it("rules and tax years", () => {
    for (const r of c.rules_for) {
      if ("error" in r.output) expect(() => rulesFor(r.fy)).toThrow();
      else {
        const got = rulesFor(r.fy);
        for (const k of [
          "ltcg_exempt",
          "stcg_equity_rate",
          "ltcg_equity_rate",
          "ltcg_other_rate",
          "standard_deduction",
          "rebate_limit",
          "rebate_max",
          "cess",
          "surcharge_from",
          "surcharge_cap_gains",
        ]) {
          expect(got[k as keyof TaxRules]).toBe(r.output.ok[k]);
        }
        same(got.slabs, unInf(r.output.ok).slabs);
        same(got.surcharge_tiers, r.output.ok.surcharge_tiers);
      }
    }
    for (const f of c.fy) {
      expect(fyOf(f.day)).toBe(f.fy);
      expect(fyLabel(fyOf(f.day))).toBe(f.label);
    }
  });
  it("classification", () => {
    for (const x of c.classify) {
      if (x.term) {
        expect(term(x.bucket, x.acquired_on, x.sold_on)).toBe(x.term);
        expect(turnsLongTermOn(x.bucket, x.acquired_on)).toBe(x.long_on);
      } else if (x.grand) expect(grandfatheredCost(100, 150, 120)).toBe(x.out);
      else expect(mfBucket(x.mf[0], x.mf[1], x.mf[2])).toBe(x.out);
    }
  });
  it("slab tax and income tax", () => {
    for (const s of c.slab_tax) expect(slabTax(s.income, rules26)).toBe(s.tax);
    for (const t of c.income_tax) same(incomeTax(t.args, rules26), t.output);
  });
  it("realised rows and open lots", () => {
    for (const x of c.realise) {
      const rate = rateOf(x.fx);
      check(x.output, () =>
        realise(x.lots as TaxLot[], x.sales as TaxSale[], x.fmv_2018, rate, x.fx_rule),
      );
      check(x.open, () => openLots(x.lots, x.sales));
    }
  });
  it("netting, set-off and carry-forward", () => {
    for (const x of c.net_gains) {
      const r = rulesFor(x.fy);
      const net = netGains(x.rows, r, x.fy, x.carried);
      same(net, x.output);
      same(inputs(net, 250_000), x.inputs);
      same(incomeTax(inputs(net, 250_000), r), x.tax);
    }
  });
  it("harvest ideas", () => {
    for (const x of c.harvest)
      same(harvest(x.lots, x.prices, x.as_of, rules26, x.realised), x.output);
  });
  it("Schedule FA", () => {
    for (const x of c.schedule_fa) {
      check(x.output, () => scheduleFa(x.lots, x.sales, x.cy, x.closes, rateOf(x.fx)));
    }
  });
});
