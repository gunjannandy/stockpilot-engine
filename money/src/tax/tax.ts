// Indian capital-gains and income-tax maths for a resident individual on the new regime: a port of
// py/stockpilot/analysis/tax.py. Data shapes stay snake_case, as in the Python, so a captured case replays as is.
// Rates and limits come from rules/tax-rules.json, picked by date.

import rulesFile from "../../rules/tax-rules.json";
import { addDays, compareDays, type Day, daysInMonth } from "../core/dates";
import { canon, isForeign } from "../core/kinds";
import { pySum } from "../core/round";

export const GRANDFATHER_DATE: Day = "2018-02-01"; // lots bought before this use the 31 Jan 2018 value
export const SPECIFIED_MF_FROM: Day = "2023-04-01"; // debt-fund units bought on or after this are always short-term
export const CARRY_YEARS = 8;
const MONTHS: Record<string, number> = { equity: 12, gold_etf: 12, other: 24, foreign: 24 };
export const SHORT_POOLS = ["stcg_slab", "stcg_equity"] as const;
export const LONG_POOLS = ["ltcg_other", "ltcg_equity"] as const;
type Pool = (typeof SHORT_POOLS)[number] | (typeof LONG_POOLS)[number];

export class OversoldError extends Error {
  override name = "OversoldError";
}
export class MissingRate extends Error {
  override name = "MissingRate";
}

export type TaxRules = {
  act: string;
  from_fy: number;
  ltcg_exempt: number;
  stcg_equity_rate: number;
  ltcg_equity_rate: number;
  ltcg_other_rate: number;
  slabs: [number | null, number][];
  standard_deduction: number;
  rebate_limit: number;
  rebate_max: number;
  cess: number;
  surcharge_from: number;
  surcharge_tiers: [number, number][];
  surcharge_cap_gains: number;
};

const SETS = (rulesFile.sets as TaxRules[]).slice().sort((a, b) => a.from_fy - b.from_fy);

/** The rule set in force for a tax year: the latest one that starts at or before it. */
export function rulesFor(taxYear: number, sets: TaxRules[] = SETS): TaxRules {
  const hit = sets.filter((s) => s.from_fy <= taxYear).pop();
  if (!hit) {
    throw new Error(
      `no rule set for FY ${taxYear}-${String((taxYear + 1) % 100).padStart(2, "0")}: capital-gains rates differ before July 2024`,
    );
  }
  return hit;
}

/** The rule set in force on a calendar day (tax year starts 1 April). */
export const rulesOn = (day: Day, sets?: TaxRules[]): TaxRules => rulesFor(fyOf(day), sets);

export type TaxLot = {
  id: number | string;
  symbol: string;
  isin: string;
  kind?: string | null;
  bucket?: string | null;
  acquired_on: Day;
  quantity: number;
  cost_per_unit: number;
  currency?: string | null;
};
export type TaxSale = {
  symbol: string;
  isin: string;
  sold_on: Day;
  quantity: number;
  price_per_unit: number;
  currency?: string | null;
  expenses?: number | null;
};
export type Row = {
  lot_id: number | string;
  symbol: string;
  isin: string;
  kind: string | null | undefined;
  bucket: string;
  acquired_on: Day;
  sold_on: Day;
  quantity: number;
  cost: number;
  proceeds: number;
  expenses: number;
  gain: number;
  grandfathered: boolean;
  term: string;
};
export type RateOn = ((day: Day) => number | null | undefined) | null | undefined;

export const fyOf = (day: Day): number => {
  const y = Number(day.slice(0, 4));
  return Number(day.slice(5, 7)) >= 4 ? y : y - 1;
};
export const fyLabel = (fy: number): string => `${fy}-${String((fy + 1) % 100).padStart(2, "0")}`;

function addMonths(day: Day, months: number): Day {
  const total = Number(day.slice(5, 7)) - 1 + months;
  const year = Number(day.slice(0, 4)) + Math.floor(total / 12);
  const month = (total % 12) + 1;
  const dd = Math.min(Number(day.slice(8, 10)), daysInMonth(year, month));
  return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(dd).padStart(2, "0")}`;
}
const monthEndBefore = (day: Day): Day => addDays(`${day.slice(0, 8)}01`, -1);

// --- classification ---------------------------------------------------------------------------

export function mfBucket(category: string | null | undefined, acquiredOn: Day, name = ""): string {
  const c = (category ?? "").toLowerCase();
  const n = name.toLowerCase();
  if (c.startsWith("equity scheme")) return "equity";
  if (c.startsWith("hybrid scheme")) {
    const eq = ["arbitrage", "aggressive", "equity savings", "multi asset"].some((k) =>
      c.includes(k),
    );
    return eq && !c.includes("balanced") ? "equity" : "other";
  }
  if (c.includes("gold") || n.includes("gold"))
    return c.includes("etf") || n.includes("etf") ? "gold_etf" : "other";
  if (c.startsWith("debt scheme"))
    return compareDays(acquiredOn, SPECIFIED_MF_FROM) >= 0 ? "specified_mf" : "other";
  if (
    (c.includes("index") || c.includes("etf")) &&
    ["nifty", "sensex", "bse 500", "equity"].some((k) => n.includes(k)) &&
    !c.includes("overseas") &&
    !n.includes("debt") &&
    !n.includes("gilt")
  )
    return "equity";
  return "other";
}

export function bucketOf(lot: Pick<TaxLot, "bucket" | "kind" | "currency">): string {
  if (lot.bucket) return lot.bucket;
  if (isForeign(lot)) return "foreign";
  return canon(lot.kind || "equity") === "equity" ? "equity" : "other";
}

export function term(bucket: string, acquiredOn: Day, soldOn: Day): "short" | "long" {
  if (bucket === "specified_mf") return "short";
  return compareDays(soldOn, addMonths(acquiredOn, MONTHS[bucket] as number)) > 0
    ? "long"
    : "short";
}

/** The first day a sale is long-term; null for a bucket that never is. */
export function turnsLongTermOn(bucket: string, acquiredOn: Day): Day | null {
  if (bucket === "specified_mf") return null;
  return addDays(addMonths(acquiredOn, MONTHS[bucket] as number), 1);
}

/** s.90(7): the higher of actual cost and the lower of the 31 Jan 2018 value and the sale price. */
export const grandfatheredCost = (actual: number, fmv2018: number, sale: number): number =>
  Math.max(actual, Math.min(fmv2018, sale));

// --- FIFO matching ----------------------------------------------------------------------------

const EPS = 1e-9;

function fifo(lots: TaxLot[], sales: TaxSale[]) {
  const left = new Map<number | string, number>(lots.map((l) => [l.id, Number(l.quantity)]));
  const byIsin = new Map<string, TaxLot[]>();
  const sortedLots = [...lots].sort(
    (a, b) => compareDays(a.acquired_on, b.acquired_on) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0),
  );
  for (const lot of sortedLots) {
    const arr = byIsin.get(lot.isin) ?? [];
    arr.push(lot);
    byIsin.set(lot.isin, arr);
  }
  const allocs: [TaxLot, TaxSale, number][] = [];
  const sortedSales = sales
    .map((s, i) => [s, i] as const)
    .sort((a, b) => compareDays(a[0].sold_on, b[0].sold_on) || a[1] - b[1]);
  for (const [sale] of sortedSales) {
    let need = Number(sale.quantity);
    for (const lot of byIsin.get(sale.isin) ?? []) {
      if (need <= EPS) break;
      if (compareDays(lot.acquired_on, sale.sold_on) > 0 || (left.get(lot.id) as number) <= EPS)
        continue;
      const take = Math.min(need, left.get(lot.id) as number);
      left.set(lot.id, (left.get(lot.id) as number) - take);
      need -= take;
      allocs.push([lot, sale, take]);
    }
    if (need > EPS) {
      throw new OversoldError(
        `${sale.symbol} (${sale.isin}): sold ${sale.quantity} on ${sale.sold_on}, but the lots on file are short by ${need}`,
      );
    }
  }
  return { allocs, left };
}

export function openLots(lots: TaxLot[], sales: TaxSale[]): TaxLot[] {
  const { left } = fifo(lots, sales);
  return lots
    .filter((l) => (left.get(l.id) as number) > EPS)
    .map((l) => ({ ...l, quantity: left.get(l.id) as number }));
}

function rate(rateOn: RateOn, day: Day, rule: string): number {
  const when = rule === "prior_month_end" ? monthEndBefore(day) : day;
  const r = rateOn ? rateOn(when) : null;
  if (r === null || r === undefined) throw new MissingRate(`no USD/INR rate on or before ${when}`);
  return r;
}

export function realise(
  lots: TaxLot[],
  sales: TaxSale[],
  fmv2018: Record<string, number> = {},
  rateOn?: RateOn,
  fxRule = "prior_month_end",
): Row[] {
  const rows: Row[] = [];
  for (const [lot, sale, qty] of fifo(lots, sales).allocs) {
    const bucket = bucketOf(lot);
    let costUnit = Number(lot.cost_per_unit);
    let grand = false;
    if (
      bucket === "equity" &&
      compareDays(lot.acquired_on, GRANDFATHER_DATE) < 0 &&
      lot.isin in fmv2018
    ) {
      costUnit = grandfatheredCost(
        costUnit,
        Number(fmv2018[lot.isin]),
        Number(sale.price_per_unit),
      );
      grand = true;
    }
    const costFx = (lot.currency || "INR") === "INR" ? 1 : rate(rateOn, lot.acquired_on, fxRule);
    const saleFx = (sale.currency || "INR") === "INR" ? 1 : rate(rateOn, sale.sold_on, fxRule);
    const cost = qty * costUnit * costFx;
    const proceeds = qty * Number(sale.price_per_unit) * saleFx;
    const expenses = ((Number(sale.expenses || 0) * qty) / Number(sale.quantity)) * saleFx;
    rows.push({
      lot_id: lot.id,
      symbol: lot.symbol,
      isin: lot.isin,
      kind: lot.kind,
      bucket,
      acquired_on: lot.acquired_on,
      sold_on: sale.sold_on,
      quantity: qty,
      cost,
      proceeds,
      expenses,
      gain: proceeds - cost - expenses,
      grandfathered: grand,
      term: term(bucket, lot.acquired_on, sale.sold_on),
    });
  }
  return rows;
}

// --- netting ----------------------------------------------------------------------------------

function poolOf(row: Row): Pool {
  if (row.term === "short") return row.bucket === "equity" ? "stcg_equity" : "stcg_slab";
  return row.bucket === "equity" ? "ltcg_equity" : "ltcg_other";
}

function absorb(pools: Record<Pool, number>, order: readonly Pool[], loss: number): number {
  for (const name of order) {
    if (loss <= 0) break;
    const used = Math.min(loss, Math.max(pools[name], 0));
    pools[name] -= used;
    loss -= used;
  }
  return loss;
}

export type Carried = { year: number | null; stcl: number; ltcl: number };
export type Net = Record<Pool, number> & {
  expired: Carried[];
  carry_forward: { stcl: number; ltcl: number; items: Carried[] };
};

/** Short-term loss meets short-term gain, then long-term gain; long-term loss meets only long-term gain;
 *  carried losses come last, oldest first (s.108, 109, 111). */
export function netGains(
  rows: Row[],
  _rules: TaxRules,
  taxYear: number | null = null,
  carried: Partial<Carried>[] | null = null,
): Net {
  const pools: Record<Pool, number> = {
    stcg_slab: 0,
    stcg_equity: 0,
    ltcg_other: 0,
    ltcg_equity: 0,
  };
  for (const row of rows) pools[poolOf(row)] += row.gain;
  let stcl = -pySum(SHORT_POOLS.map((p) => Math.min(pools[p], 0)));
  let ltcl = -pySum(LONG_POOLS.map((p) => Math.min(pools[p], 0)));
  for (const p of [...SHORT_POOLS, ...LONG_POOLS]) pools[p] = Math.max(pools[p], 0);
  stcl = absorb(pools, [...SHORT_POOLS, ...LONG_POOLS], stcl);
  ltcl = absorb(pools, LONG_POOLS, ltcl);
  const items: Carried[] = [];
  const expired: Carried[] = [];
  const order = [...(carried ?? [])].sort((a, b) => (a.year as number) - (b.year as number));
  for (const item of order) {
    if (taxYear !== null && taxYear - (item.year as number) > CARRY_YEARS) {
      expired.push(item as Carried);
      continue;
    }
    const s = absorb(pools, [...SHORT_POOLS, ...LONG_POOLS], item.stcl ?? 0);
    const l = absorb(pools, LONG_POOLS, item.ltcl ?? 0);
    if (s || l) items.push({ year: item.year as number, stcl: s, ltcl: l });
  }
  if (stcl || ltcl) items.push({ year: taxYear, stcl, ltcl });
  return {
    ...pools,
    expired,
    carry_forward: {
      stcl: pySum(items.map((i) => i.stcl)),
      ltcl: pySum(items.map((i) => i.ltcl)),
      items,
    },
  };
}

export type TaxInputs = {
  slab_income: number;
  stcg_equity: number;
  ltcg_equity: number;
  ltcg_other: number;
};

export function inputs(net: Net, slabIncome = 0): TaxInputs {
  return {
    slab_income: slabIncome + net.stcg_slab,
    stcg_equity: net.stcg_equity,
    ltcg_equity: net.ltcg_equity,
    ltcg_other: net.ltcg_other,
  };
}

// --- tax --------------------------------------------------------------------------------------

export function slabTax(income: number, rules: TaxRules): number {
  let tax = 0;
  let lower = 0;
  for (const [upperRaw, r] of rules.slabs) {
    const upper = upperRaw ?? Number.POSITIVE_INFINITY;
    if (income > lower) tax += (Math.min(income, upper) - lower) * r;
    lower = upper;
  }
  return tax;
}

function surchargeRate(totalIncome: number, rules: TaxRules): number {
  for (const [above, r] of rules.surcharge_tiers) if (totalIncome > above) return r;
  return 0;
}

function core(
  slabIncome: number,
  dividend: number,
  stcgEquity: number,
  ltcgEquity: number,
  ltcgOther: number,
  rules: TaxRules,
) {
  const totalIncome = slabIncome + dividend + stcgEquity + ltcgEquity + ltcgOther;
  let slab = slabTax(slabIncome + dividend, rules);
  let salarySlab = slabTax(slabIncome, rules);
  if (totalIncome <= rules.rebate_limit) {
    const rebate = Math.min(slab, rules.rebate_max);
    slab -= rebate;
    salarySlab = Math.max(salarySlab - rebate, 0);
  } else {
    slab = Math.min(slab, totalIncome - rules.rebate_limit);
    salarySlab = Math.min(salarySlab, slab);
  }
  const special = {
    stcg_equity: stcgEquity * rules.stcg_equity_rate,
    ltcg_equity: Math.max(ltcgEquity - rules.ltcg_exempt, 0) * rules.ltcg_equity_rate,
    ltcg_other: ltcgOther * rules.ltcg_other_rate,
  };
  const rate = surchargeRate(totalIncome, rules);
  const capped = Math.min(rate, rules.surcharge_cap_gains);
  const surcharge =
    salarySlab * rate +
    (slab - salarySlab) * capped +
    pySum([special.stcg_equity, special.ltcg_equity, special.ltcg_other]) * capped;
  return { slab_tax: slab, ...special, surcharge, total_income: totalIncome };
}

function trim(excess: number, parts: number[]): number[] {
  return parts.map((value) => {
    const cut = Math.min(value, excess);
    excess -= cut;
    return value - cut;
  });
}

export type IncomeTax = {
  slab_tax: number;
  stcg_equity: number;
  ltcg_equity: number;
  ltcg_other: number;
  surcharge: number;
  cess: number;
  total: number;
  warnings: string[];
};

export function incomeTax(
  a: {
    slab_income?: number;
    stcg_equity?: number;
    ltcg_equity?: number;
    ltcg_other?: number;
    dividend?: number;
  },
  rules: TaxRules,
): IncomeTax {
  const slabIncome = a.slab_income ?? 0;
  const stcgEquity = a.stcg_equity ?? 0;
  const ltcgEquity = a.ltcg_equity ?? 0;
  const ltcgOther = a.ltcg_other ?? 0;
  const dividend = a.dividend ?? 0;
  const c = core(slabIncome, dividend, stcgEquity, ltcgEquity, ltcgOther, rules);
  let surcharge = c.surcharge;
  const base = c.slab_tax + c.stcg_equity + c.ltcg_equity + c.ltcg_other;
  const total = c.total_income;
  const hit = rules.surcharge_tiers.find(([above]) => total > above);
  if (hit) {
    const threshold = hit[0];
    const [slabT, divT, otherT, stcgT, ltcgT] = trim(total - threshold, [
      slabIncome,
      dividend,
      ltcgOther,
      stcgEquity,
      ltcgEquity,
    ]) as [number, number, number, number, number];
    const at = core(slabT, divT, stcgT, ltcgT, otherT, rules);
    const limit =
      at.slab_tax +
      at.stcg_equity +
      at.ltcg_equity +
      at.ltcg_other +
      at.surcharge +
      (total - threshold);
    surcharge = Math.max(Math.min(surcharge, limit - base), 0);
  }
  const beforeCess = base + surcharge;
  const cess = beforeCess * rules.cess;
  return {
    slab_tax: c.slab_tax,
    stcg_equity: c.stcg_equity,
    ltcg_equity: c.ltcg_equity,
    ltcg_other: c.ltcg_other,
    surcharge,
    cess,
    total: beforeCess + cess,
    warnings: [],
  };
}

// --- harvest ----------------------------------------------------------------------------------

export type Harvest = {
  gain_room: number;
  gain_candidates: { symbol: string; quantity: number; gain: number; future_tax_saved: number }[];
  gain_room_left: number;
  loss_candidates: { symbol: string; quantity: number; loss: number }[];
};

/** What could be sold today to use the free long-term room, and which losers could be sold to bank a loss. */
export function harvest(
  open: TaxLot[],
  prices: Record<string, number>,
  asOf: Day,
  rules: TaxRules,
  realisedLtcgEquity = 0,
): Harvest {
  const room = Math.max(rules.ltcg_exempt - realisedLtcgEquity, 0);
  const bySymbol = new Map<string, TaxLot[]>();
  const sorted = [...open].sort(
    (a, b) => compareDays(a.acquired_on, b.acquired_on) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0),
  );
  for (const lot of sorted) {
    if (bucketOf(lot) === "equity" && prices[lot.symbol]) {
      const arr = bySymbol.get(lot.symbol) ?? [];
      arr.push(lot);
      bySymbol.set(lot.symbol, arr);
    }
  }
  const candidates: Harvest["gain_candidates"] = [];
  let left = room;
  for (const [symbol, lots] of bySymbol) {
    const price = prices[symbol] as number;
    let qty = 0;
    let gain = 0;
    for (const lot of lots) {
      if (term("equity", lot.acquired_on, asOf) !== "long" || left <= 0) break;
      const unit = price - lot.cost_per_unit;
      const take = unit <= 0 ? lot.quantity : Math.min(lot.quantity, Math.floor(left / unit));
      qty += take;
      gain += take * unit;
      left -= take * unit;
      if (take < lot.quantity) break;
    }
    if (qty > 0 && gain > 0)
      candidates.push({
        symbol,
        quantity: qty,
        gain,
        future_tax_saved: gain * rules.ltcg_equity_rate,
      });
  }
  const losers: Harvest["loss_candidates"] = [];
  for (const [symbol, lots] of bySymbol) {
    const pnl = pySum(lots.map((l) => ((prices[symbol] as number) - l.cost_per_unit) * l.quantity));
    if (pnl < 0) losers.push({ symbol, quantity: pySum(lots.map((l) => l.quantity)), loss: -pnl });
  }
  return {
    gain_room: room,
    gain_candidates: candidates,
    gain_room_left: Math.max(left, 0),
    loss_candidates: losers.sort((a, b) => b.loss - a.loss),
  };
}

// --- Schedule FA ------------------------------------------------------------------------------

export type FaRow = {
  symbol: string;
  isin: string;
  units_at_close: number;
  initial_value: number;
  peak_value: number | null;
  closing_value: number | null;
  gross_proceeds: number;
  note: string;
};

/** Foreign shares for the calendar year: value at purchase, peak, close and sale proceeds, in rupees. */
export function scheduleFa(
  lots: TaxLot[],
  sales: TaxSale[],
  calendarYear: number,
  closes: Record<string, Record<Day, number>>,
  rateOn: RateOn,
): FaRow[] {
  const start = `${calendarYear}-01-01`;
  const end = `${calendarYear}-12-31`;
  const foreign = lots.filter((l) => isForeign(l));
  const isins = new Set(foreign.map((l) => l.isin));
  const { allocs } = fifo(
    foreign,
    sales.filter((s) => isins.has(s.isin)),
  );
  const fx = (day: Day) => {
    const r = rateOn ? rateOn(day) : null;
    if (r === null || r === undefined) throw new MissingRate(`no USD/INR rate on or before ${day}`);
    return r;
  };
  const unitsOn = (symbol: string, day: Day) =>
    pySum(
      foreign
        .filter((l) => l.symbol === symbol && compareDays(l.acquired_on, day) <= 0)
        .map((l) => l.quantity),
    ) -
    pySum(
      allocs
        .filter(([l, s]) => l.symbol === symbol && compareDays(s.sold_on, day) <= 0)
        .map(([, , q]) => q),
    );
  const rows: FaRow[] = [];
  for (const symbol of [...new Set(foreign.map((l) => l.symbol))].sort()) {
    const mine = foreign.filter((l) => l.symbol === symbol);
    const held = mine.filter(
      (l) =>
        compareDays(l.acquired_on, end) <= 0 &&
        (compareDays(l.acquired_on, start) >= 0 ||
          l.quantity -
            pySum(
              allocs
                .filter(([lot, s]) => lot.id === l.id && compareDays(s.sold_on, start) < 0)
                .map(([, , q]) => q),
            ) >
            EPS),
    );
    if (!held.length) continue;
    const series = Object.entries(closes[symbol] ?? {}).filter(
      ([dd]) => compareDays(dd, start) >= 0 && compareDays(dd, end) <= 0,
    );
    let note = "";
    let peak: number | null = null;
    let closing: number | null = null;
    if (series.length) {
      peak = Math.max(...series.map(([dd, p]) => unitsOn(symbol, dd) * p * fx(dd)));
      const last = series.map(([dd]) => dd).reduce((a, b) => (compareDays(a, b) >= 0 ? a : b));
      closing =
        unitsOn(symbol, end) * ((closes[symbol] as Record<Day, number>)[last] as number) * fx(end);
    } else {
      note = "needs price history for this share: peak and closing value left blank";
    }
    rows.push({
      symbol,
      isin: (mine[0] as TaxLot).isin,
      units_at_close: unitsOn(symbol, end),
      initial_value: pySum(held.map((l) => l.quantity * l.cost_per_unit * fx(l.acquired_on))),
      peak_value: peak,
      closing_value: closing,
      gross_proceeds: pySum(
        allocs
          .filter(
            ([l, s]) =>
              l.symbol === symbol &&
              compareDays(s.sold_on, start) >= 0 &&
              compareDays(s.sold_on, end) <= 0,
          )
          .map(([, s, q]) => q * s.price_per_unit * fx(s.sold_on)),
      ),
      note,
    });
  }
  return rows;
}
