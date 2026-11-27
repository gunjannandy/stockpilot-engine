// His own record: what the father's own stock trades (not smallcase's) have shown over the years.
// A trade here is one sale: a sale that used several lots counts once, with the gain added up and the
// holding days averaged by quantity. Only closed trades count; what is still held says nothing yet.
// A port of Python `book/record.py`; every sum is Python's `sum`, every rounding Python's `round`.
import { addDays, compareDays, type Day, daysBetween, month } from "../core/dates";
import { pyFixed, pyRound, pySum } from "../core/round";

export const MIN_TRADES = 3; // fewer closed trades than this say nothing yet
export const LATER_DAYS = 91; // "the next 3 months"

/** One lot matched to one sale (first in, first out), in rupees, with the route that bought the lot. */
export type Pair = {
  route: string; // kite (the father placed it) | smallcase
  symbol: string;
  acquiredOn: Day;
  soldOn: Day;
  quantity: number;
  cost: number;
  proceeds: number;
  gain: number;
};

/** A sorted (day, value) list that answers "the last value on or before a day". */
export class Series {
  private readonly days: Day[];
  private readonly values: number[];
  constructor(rows: readonly (readonly [Day, number])[]) {
    this.days = rows.map(([d]) => d);
    this.values = rows.map(([, v]) => v);
  }
  private index(day: Day): number {
    let lo = 0;
    let hi = this.days.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (compareDays(day, this.days[mid] as Day) < 0) hi = mid;
      else lo = mid + 1;
    }
    return lo;
  }
  on(day: Day): number | null {
    const i = this.index(day);
    return i ? (this.values[i - 1] as number) : null;
  }
  /** The value on `day`, or on a day up to `within` days earlier; null when the series has nothing that close. */
  near(day: Day, within = 7): number | null {
    const i = this.index(day);
    return i && daysBetween(day, this.days[i - 1] as Day) <= within
      ? (this.values[i - 1] as number)
      : null;
  }
}

export type RecordInput = {
  pairs: readonly Pair[];
  asOf: Day;
  /** Adjusted closes per symbol, for the winners' symbols. */
  prices: Record<string, Series>;
  nifty: Series;
};

type Trade = {
  symbol: string;
  soldOn: Day;
  quantity: number;
  cost: number;
  proceeds: number;
  gain: number;
  days: number;
  lots: [Day, number][];
};

export type OwnRecord = {
  asOf: Day;
  closed: number;
  winners: number;
  losers: number;
  winRate: number | null;
  avgDaysWinners: number | null;
  avgDaysLosers: number | null;
  soldEarly: { checked: number; roseAfter: number; share: number | null };
  vsNifty: { checked: number; beat: number; share: number | null; averageGapPoints: number | null };
  byMonth: { month: string; closed: number; winners: number; gain: number }[];
  lines: string[];
};

/** One row per sale: cost, proceeds, quantity, average holding days, and the lots' dates (for the Nifty). */
function tradesOf(pairs: readonly Pair[], asOf: Day): Trade[] {
  const grouped = new Map<string, Pair[]>();
  for (const p of pairs) {
    if (p.route !== "kite" || compareDays(p.soldOn, asOf) > 0) continue;
    const k = `${p.symbol}\u0000${p.soldOn}`;
    const list = grouped.get(k) ?? [];
    grouped.set(k, list);
    list.push(p);
  }
  return [...grouped.values()]
    .map((rows, i) => ({ rows, i }))
    .sort(
      (a, b) => compareDays((a.rows[0] as Pair).soldOn, (b.rows[0] as Pair).soldOn) || a.i - b.i,
    )
    .map(({ rows }) => {
      const first = rows[0] as Pair;
      const qty = pySum(rows.map((r) => r.quantity));
      return {
        symbol: first.symbol,
        soldOn: first.soldOn,
        quantity: qty,
        cost: pySum(rows.map((r) => r.cost)),
        proceeds: pySum(rows.map((r) => r.proceeds)),
        gain: pySum(rows.map((r) => r.gain)),
        days: pySum(rows.map((r) => daysBetween(r.soldOn, r.acquiredOn) * r.quantity)) / qty,
        lots: rows.map((r) => [r.acquiredOn, r.cost] as [Day, number]),
      };
    });
}

const avg = (values: number[]): number | null =>
  values.length ? pyRound(pySum(values) / values.length, 1) : null;

export function buildRecord(input: RecordInput): OwnRecord {
  const { asOf } = input;
  const trades = tradesOf(input.pairs, asOf);
  const winners = trades.filter((t) => t.gain > 0);
  const losers = trades.filter((t) => t.gain <= 0);
  const out: OwnRecord = {
    asOf,
    closed: trades.length,
    winners: winners.length,
    losers: losers.length,
    winRate: trades.length ? pyRound((100 * winners.length) / trades.length, 1) : null,
    avgDaysWinners: avg(winners.map((t) => t.days)),
    avgDaysLosers: avg(losers.map((t) => t.days)),
    soldEarly: { checked: 0, roseAfter: 0, share: null },
    vsNifty: { checked: 0, beat: 0, share: null, averageGapPoints: null },
    byMonth: [],
    lines: [],
  };
  if (!trades.length) return out;

  const se = out.soldEarly;
  for (const t of winners) {
    const later = addDays(t.soldOn, LATER_DAYS);
    if (compareDays(later, asOf) > 0) continue;
    const price = input.prices[t.symbol]?.near(later) ?? null;
    if (price === null) continue;
    se.checked += 1;
    se.roseAfter += price > t.proceeds / t.quantity ? 1 : 0;
  }
  se.share = se.checked ? pyRound((100 * se.roseAfter) / se.checked, 1) : null;

  const gaps: number[] = [];
  for (const t of trades) {
    const end = input.nifty.on(t.soldOn);
    const starts = t.lots.map(([on, cost]) => [input.nifty.on(on), cost] as const);
    if (!end || !starts.every(([s]) => s) || !t.cost) continue;
    const niftyReturn = pySum(starts.map(([s, cost]) => cost * (end / (s as number) - 1))) / t.cost;
    gaps.push((t.proceeds / t.cost - 1 - niftyReturn) * 100);
  }
  const vn = out.vsNifty;
  vn.checked = gaps.length;
  vn.beat = gaps.filter((g) => g > 0).length;
  if (gaps.length) {
    vn.share = pyRound((100 * vn.beat) / gaps.length, 1);
    vn.averageGapPoints = pyRound(pySum(gaps) / gaps.length, 2);
  }

  const months = new Map<string, { closed: number; winners: number; gain: number }>();
  for (const t of trades) {
    const k = month(t.soldOn);
    const m = months.get(k) ?? { closed: 0, winners: 0, gain: 0.0 };
    months.set(k, m);
    m.closed += 1;
    m.winners += t.gain > 0 ? 1 : 0;
    m.gain += t.gain;
  }
  out.byMonth = [...months.entries()]
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    .map(([k, v]) => ({
      month: k,
      closed: v.closed,
      winners: v.winners,
      gain: pyRound(v.gain, 2),
    }));

  if (trades.length >= MIN_TRADES) {
    const rate = pyFixed(out.winRate as number, 0);
    out.lines.push(
      winners.length && losers.length
        ? `Of the ${trades.length} stock trades you closed, ${rate}% made money. Winners were held ${pyFixed(out.avgDaysWinners as number, 0)} days on average, losers ${pyFixed(out.avgDaysLosers as number, 0)}.`
        : `Of the ${trades.length} stock trades you closed, ${rate}% made money.`,
    );
    if (se.share !== null) {
      const said = se.share === 50 ? "Half" : `${pyFixed(se.share, 0)}%`;
      out.lines.push(
        `${said} of the winners you sold went on to gain more within the next 3 months.`,
      );
    }
  }
  return out;
}
