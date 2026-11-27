// XIRR: the yearly return that makes a dated list of cash flows net to zero (365-day years).
// Per holding and for the portfolio, against the Nifty over the same cash flows.
import { type Day, daysBetween } from "../core/dates";

/** Money in is negative (a buy), money out is positive (a sell, or today's value). */
export type Flow = { day: Day; amount: number };

function npv(rate: number, flows: readonly Flow[], t0: Day): number {
  let s = 0;
  for (const f of flows) s += f.amount / (1 + rate) ** (daysBetween(f.day, t0) / 365);
  return s;
}

/** Null when the flows have no sign change or no answer exists. Bisection: slow but cannot diverge. */
export function xirr(flows: readonly Flow[]): number | null {
  const fl = flows.filter((f) => f.amount !== 0);
  if (!fl.some((f) => f.amount < 0) || !fl.some((f) => f.amount > 0)) return null;
  const t0 = fl.reduce((m, f) => (f.day < m ? f.day : m), (fl[0] as Flow).day);
  let lo = -0.999999;
  let hi = 1;
  while (npv(hi, fl, t0) > 0 && hi < 1e6) hi *= 2;
  const fLo = npv(lo, fl, t0);
  if (fLo * npv(hi, fl, t0) > 0) return null;
  for (let i = 0; i < 200; i++) {
    const mid = (lo + hi) / 2;
    const v = npv(mid, fl, t0);
    if (Math.abs(v) < 1e-9 || hi - lo < 1e-12) return mid;
    if (v * fLo > 0) lo = mid;
    else hi = mid;
  }
  return (lo + hi) / 2;
}

/** The same cash flows put into the Nifty: each buy buys index units at that day's level, each sell sells
 *  units at that day's level (units may go short; the sum is what counts), and what is left is valued at
 *  the end day's level. `flows` excludes the final value; `endValue` is the holding's value on `end`. */
export function niftyXirr(
  flows: readonly Flow[],
  endValue: number,
  end: Day,
  niftyOn: (day: Day) => number | null,
): number | null {
  let units = 0;
  for (const f of flows) {
    const level = niftyOn(f.day);
    if (!level) return null;
    units += -f.amount / level;
  }
  const endLevel = niftyOn(end);
  if (!endLevel) return null;
  void endValue;
  return xirr([...flows, { day: end, amount: units * endLevel }]);
}

export type Return = { holding: number | null; nifty: number | null; edge: number | null };

/** A holding's XIRR and the Nifty's over the same flows; `edge` is the difference. */
export function returnVsNifty(
  flows: readonly Flow[],
  endValue: number,
  end: Day,
  niftyOn: (day: Day) => number | null,
): Return {
  const holding = xirr([...flows, { day: end, amount: endValue }]);
  const nifty = niftyXirr(flows, endValue, end, niftyOn);
  return { holding, nifty, edge: holding !== null && nifty !== null ? holding - nifty : null };
}
