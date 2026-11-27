// RSUs: value, tax, expected vests, and the one "estimated" lot for shares the documents do not show yet.
// A port of Python `trades/rsu.py` (expected_vests, vests_from_payslips) and `book/rsu.py`.
import { type Day, daysInMonth, toOrdinal } from "../core/dates";
import { pyRound } from "../core/round";

export type Vest = {
  day: Day;
  quantity: number; // shares
  priceUsd: number | null;
  status: "confirmed" | "expected";
  estimated?: boolean;
};
export type SplitAction = { exDate: Day; numerator: number; denominator: number };

export function addMonths(day: Day, months: number): Day {
  const idx = Number(day.slice(0, 4)) * 12 + Number(day.slice(5, 7)) - 1 + months;
  const y = Math.floor(idx / 12);
  const m = (idx % 12) + 1;
  const d = Math.min(Number(day.slice(8, 10)), daysInMonth(y, m));
  return `${String(y).padStart(4, "0")}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

/** One expected vest per quarter after the latest confirmed one, up to `through`, repeating its size
 *  and scaled by any split that falls in between. */
export function expectedVests(
  confirmed: readonly Vest[],
  through: Day,
  actions: readonly SplitAction[] = [],
  everyMonths = 3,
): Vest[] {
  const vests = confirmed
    .filter((v) => v.status === "confirmed" && !v.estimated)
    .sort((a, b) => (a.day < b.day ? -1 : a.day > b.day ? 1 : 0));
  const last = vests[vests.length - 1];
  if (!last) return [];
  let qty = last.quantity;
  const out: Vest[] = [];
  for (let step = 1; ; step++) {
    const when = addMonths(last.day, everyMonths * step);
    if (when > through) break;
    const from = addMonths(last.day, everyMonths * (step - 1));
    for (const a of actions)
      if (from < a.exDate && a.exDate <= when) qty *= a.numerator / a.denominator;
    out.push({ day: when, quantity: pyRound(qty, 4), priceUsd: null, status: "expected" });
  }
  return out;
}

/** Months whose payslip shows a perquisite are vest months: shares = perquisite / price that month. */
export function vestsFromPayslips(
  slips: readonly [string, number][],
  priceInr: (month: string) => number,
): Vest[] {
  return [...slips]
    .sort((a, b) => (a[0] < b[0] ? -1 : 1))
    .filter(([, perq]) => perq > 0)
    .map(([m, perq]) => ({
      day: `${m}-15`,
      quantity: pyRound(perq / priceInr(m), 4),
      priceUsd: null,
      status: "expected" as const,
    }));
}

export type RsuLot = {
  acquiredOn: Day;
  quantity: number;
  costUsd: number | null;
  estimated?: boolean;
};

/** Documents stop short of the current share count: the gap becomes one lot marked estimated, dated
 *  `asOf`, until a newer statement arrives. A count at or below the documents adds nothing. */
export function withEstimatedGap(
  lots: readonly RsuLot[],
  currentShares: number | null,
  asOf: Day,
  priceUsd: number | null,
): RsuLot[] {
  if (currentShares === null) return [...lots];
  const documented = lots.reduce((s, l) => s + l.quantity, 0);
  const gap = currentShares - documented;
  if (!(gap > 1e-6)) return [...lots];
  return [...lots, { acquiredOn: asOf, quantity: gap, costUsd: priceUsd, estimated: true }];
}

export type RsuTaxRule = {
  /** Days held after which a gain is long term. */
  longTermDays: number;
  /** Rates on the rupee gain: short and long term (fractions, e.g. 0.3 and 0.125). */
  shortRate: number;
  longRate: number;
};

export type RsuView = {
  shares: number;
  valueInr: number;
  gainInr: number;
  taxInr: number; // tax if everything were sold on `asOf`
  estimatedShares: number;
  lots: {
    acquiredOn: Day;
    quantity: number;
    valueInr: number;
    gainInr: number;
    taxInr: number;
    estimated: boolean;
  }[];
};

/** Value and tax of the RSU holding on `asOf`. Cost per lot = dollars × rate of its own day. */
export function rsuView(input: {
  lots: readonly RsuLot[];
  priceUsd: number;
  rate: number; // USD/INR today
  rateOn: (day: Day) => number | null;
  rule: RsuTaxRule;
  asOf: Day;
}): RsuView {
  const view: RsuView = {
    shares: 0,
    valueInr: 0,
    gainInr: 0,
    taxInr: 0,
    estimatedShares: 0,
    lots: [],
  };
  for (const l of input.lots) {
    const value = l.quantity * input.priceUsd * input.rate;
    const costRate = input.rateOn(l.acquiredOn) || input.rate;
    const cost = l.costUsd === null ? value : l.quantity * l.costUsd * costRate;
    const gain = value - cost;
    const held = toOrdinal(input.asOf) - toOrdinal(l.acquiredOn);
    const rate = held > input.rule.longTermDays ? input.rule.longRate : input.rule.shortRate;
    const tax = gain > 0 ? gain * rate : 0;
    view.shares += l.quantity;
    view.valueInr += value;
    view.gainInr += gain;
    view.taxInr += tax;
    if (l.estimated) view.estimatedShares += l.quantity;
    view.lots.push({
      acquiredOn: l.acquiredOn,
      quantity: l.quantity,
      valueInr: value,
      gainInr: gain,
      taxInr: tax,
      estimated: Boolean(l.estimated),
    });
  }
  return view;
}
