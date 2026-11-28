// The fund screen's rules (no look): returns, rolling returns, falls, buy dots. Ported from v2.
// A series is oldest first: dates "YYYY-MM-DD" and the NAV on each.
export type Series = { dates: string[]; nav: number[] };
export type Lot = { acquired_on: string; quantity: number; cost: number };
const DAY = 86_400_000;
const YEAR = 365.25 * DAY;
const t = (d: string) => Date.parse(d);
const ok = (s: Series | null | undefined): s is Series => !!s && s.dates.length > 1;

/** Last index whose date is on or before `when` (-1 when the series starts later). */
function at(s: Series, when: number): number {
  let lo = 0;
  let hi = s.dates.length - 1;
  let r = -1;
  while (lo <= hi) {
    const m = (lo + hi) >> 1;
    if (t(s.dates[m] as string) <= when) {
      r = m;
      lo = m + 1;
    } else hi = m - 1;
  }
  return r;
}

/** Yearly rate in percent between two moments, from the NAVs on or before each. */
function rate(s: Series, from: number, to: number): number | null {
  const a = at(s, from);
  const b = at(s, to);
  if (a < 0 || b <= a) return null;
  const na = s.nav[a] as number;
  const nb = s.nav[b] as number;
  if (!(na > 0) || !(nb > 0)) return null;
  const yrs = (t(s.dates[b] as string) - t(s.dates[a] as string)) / YEAR;
  return yrs <= 0 ? null : ((nb / na) ** (1 / yrs) - 1) * 100;
}

/** Yearly rate over the last `years`; null when the fund is younger than that. */
export function cagr(s: Series | null | undefined, years: number): number | null {
  if (!ok(s)) return null;
  const end = t(s.dates[s.dates.length - 1] as string);
  const from = end - years * YEAR;
  if (t(s.dates[0] as string) > from + 10 * DAY) return null;
  return rate(s, from, end);
}

export type RollPoint = { date: string; ret: number };
/** Monthly points: the yearly rate of the `years` ending on each date. */
export function rolling(s: Series | null | undefined, years: number): RollPoint[] {
  if (!ok(s)) return [];
  const out: RollPoint[] = [];
  const last = t(s.dates[s.dates.length - 1] as string);
  const step = 30.4375 * DAY;
  for (let when = t(s.dates[0] as string) + years * YEAR; when <= last + 1; when += step) {
    const i = at(s, when);
    const r = rate(s, when - years * YEAR, when);
    if (r != null && i >= 0) out.push({ date: s.dates[i] as string, ret: r });
  }
  return out;
}

export function rollStats(r: RollPoint[]) {
  if (!r.length) return null;
  const v = r.map((x) => x.ret).sort((a, b) => a - b);
  const n = v.length;
  const median =
    n % 2 ? (v[n >> 1] as number) : ((v[n / 2 - 1] as number) + (v[n / 2] as number)) / 2;
  return {
    n,
    min: v[0] as number,
    max: v[n - 1] as number,
    median,
    positive: v.filter((x) => x > 0).length / n,
  };
}

/** Share of rolling-year windows in which the fund did better than another series. */
export function beatShare(
  fund: Series,
  other: Series | null | undefined,
  years = 1,
): number | null {
  if (!ok(other)) return null;
  let n = 0;
  let won = 0;
  for (const p of rolling(fund, years)) {
    const when = t(p.date);
    const o = rate(other, when - years * YEAR, when);
    if (o == null || t(other.dates[0] as string) > when - years * YEAR + 10 * DAY) continue;
    n++;
    if (p.ret > o) won++;
  }
  return n ? won / n : null;
}

/** Bad markets, named in plain words by the screen. Dates are the Nifty's peak and trough. */
export const MARKETS = [
  { id: "gfc", from: "2008-01-08", to: "2009-03-09" },
  { id: "covid", from: "2020-01-20", to: "2020-03-23" },
  { id: "slide22", from: "2021-10-19", to: "2022-06-17" },
] as const;

function deepest(s: Series | null | undefined, from: string, to: string): number | null {
  if (!ok(s)) return null;
  const a = at(s, t(from));
  const b = at(s, t(to));
  if (b < 0) return null;
  const start = Math.max(a, 0);
  if (a < 0 && t(s.dates[0] as string) > t(from) + 20 * DAY) return null;
  let peak = 0;
  let worst = 0;
  for (let i = start; i <= b; i++) {
    const v = s.nav[i] as number;
    if (!(v > 0)) continue;
    if (v > peak) peak = v;
    worst = Math.min(worst, v / peak - 1);
  }
  return b - start < 1 ? null : worst * 100;
}

export type Fall = { id: string; from: string; to: string; fund: number; bench: number | null };
export function falls(fund: Series, bench: Series | null | undefined): Fall[] {
  const out: Fall[] = [];
  for (const m of MARKETS) {
    const f = deepest(fund, m.from, m.to);
    if (f == null) continue;
    out.push({ id: m.id, from: m.from, to: m.to, fund: f, bench: deepest(bench, m.from, m.to) });
  }
  return out;
}

export const RANGES = ["1Y", "3Y", "5Y", "10Y", "All"] as const;
export type Range = (typeof RANGES)[number];
const RANGE_YEARS: Record<string, number> = { "1Y": 1, "3Y": 3, "5Y": 5, "10Y": 10 };
export function slice(s: Series, range: Range): Series {
  const y = RANGE_YEARS[range];
  if (!ok(s) || !y) return s;
  const from = t(s.dates[s.dates.length - 1] as string) - y * YEAR;
  const i = Math.max(at(s, from), 0);
  return { dates: s.dates.slice(i), nav: s.nav.slice(i) };
}

/** The buys, placed on the chart's own dates. */
export function buyDots(s: Series, lots: Lot[]) {
  if (!ok(s)) return [];
  const lo = t(s.dates[0] as string);
  const hi = t(s.dates[s.dates.length - 1] as string);
  return lots
    .filter((l) => t(l.acquired_on) >= lo && t(l.acquired_on) <= hi)
    .map((l) => ({ ...l, i: at(s, t(l.acquired_on)) }));
}

export type Verdict = "ahead" | "behind" | "level";
export function vs(a: number | null, b: number | null): Verdict | null {
  if (a == null || b == null) return null;
  return a - b > 1 ? "ahead" : a - b < -1 ? "behind" : "level";
}
