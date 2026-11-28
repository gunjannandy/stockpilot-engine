// Pure chart maths, ported from v2: no DOM, so it is unit-tested. Dates are "YYYY-MM-DD".
export type Ohlc = {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};
export type Point = { time: string; value: number };
export type RangeId = "5D" | "1W" | "1M" | "6M" | "1Y" | "5Y" | "All";
export const RANGES: RangeId[] = ["5D", "1W", "1M", "6M", "1Y", "5Y", "All"];

const parse = (s: string) => new Date(`${s}T00:00:00Z`);
export const addDays = (s: string, n: number) => {
  const d = parse(s);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};
const isWeekday = (s: string) => parse(s).getUTCDay() % 6 !== 0;

export function sma(bars: { time: string; close: number }[], days: number): Point[] {
  const out: Point[] = [];
  let sum = 0;
  bars.forEach((b, i) => {
    sum += b.close;
    const old = bars[i - days];
    if (old) sum -= old.close;
    if (i >= days - 1) out.push({ time: b.time, value: +(sum / days).toFixed(2) });
  });
  return out;
}

const BACK: Record<string, [number, number]> = {
  "1M": [0, 1],
  "6M": [0, 6],
  "1Y": [1, 0],
  "5Y": [5, 0],
};
/** First chart date shown for a range, never before the listing. */
export function rangeStart(range: RangeId, dates: string[]): string {
  const first = dates[0] ?? "";
  const last = dates[dates.length - 1];
  if (range === "5D") return dates[Math.max(0, dates.length - 5)] ?? first;
  if (range === "1W" && last) {
    const w = addDays(last, -7);
    return dates.find((x) => x >= w) ?? first;
  }
  const back = BACK[range];
  if (!last || !back) return first;
  const d = parse(last);
  d.setUTCFullYear(d.getUTCFullYear() - back[0]);
  d.setUTCMonth(d.getUTCMonth() - back[1]);
  const from = d.toISOString().slice(0, 10);
  return dates.find((x) => x >= from) ?? first;
}

/** Zoom factor for one wheel notch (<1 zooms in); null means plain scroll, which never zooms. */
export function wheelZoom(e: {
  ctrlKey: boolean;
  metaKey: boolean;
  deltaY: number;
}): number | null {
  if (!e.ctrlKey && !e.metaKey) return null;
  return e.deltaY > 0 ? 1.15 : 0.87;
}

export type Call = {
  low: [number, number, number];
  likely: [number, number, number];
  high: [number, number, number];
};
export type BandPoint = {
  time: string;
  lo80: number;
  hi80: number;
  lo50: number;
  hi50: number;
  mid: number;
};
const HZ: [number, number][] = [
  [0, 30],
  [1, 91],
  [2, 182],
];
const K50 = 0.674 / 1.282;

/** Forecast bands from the 10th/50th/90th percentile at 1, 3 and 6 months; spread grows with sqrt(time). */
export function bandsOf(call: Call | null, lastDate: string, lastClose: number) {
  if (!call) return null;
  const nodes = HZ.map(([i, days]) => {
    const lo = call.low[i] as number;
    const mid = call.likely[i] as number;
    const hi = call.high[i] as number;
    return {
      days,
      time: addDays(lastDate, days),
      lo80: lo,
      hi80: hi,
      mid,
      lo50: mid - (mid - lo) * K50,
      hi50: mid + (hi - mid) * K50,
    };
  });
  if (nodes.some((n) => !(n.lo80 <= n.mid && n.mid <= n.hi80))) return null;
  const z = {
    days: 0,
    lo80: lastClose,
    hi80: lastClose,
    mid: lastClose,
    lo50: lastClose,
    hi50: lastClose,
  };
  const all = [z, ...nodes];
  type F = "lo80" | "hi80" | "lo50" | "hi50" | "mid";
  const at = (d: number, f: F) => {
    const u = Math.sqrt(d);
    for (let i = 1; i < all.length; i++) {
      const a = all[i - 1] as (typeof all)[number];
      const b = all[i] as (typeof all)[number];
      if (d <= b.days) {
        const t = (u - Math.sqrt(a.days)) / (Math.sqrt(b.days) - Math.sqrt(a.days));
        return a[f] + (b[f] - a[f]) * t;
      }
    }
    return (all[all.length - 1] as (typeof all)[number])[f];
  };
  const points: BandPoint[] = [
    {
      time: lastDate,
      lo80: lastClose,
      hi80: lastClose,
      lo50: lastClose,
      hi50: lastClose,
      mid: lastClose,
    },
  ];
  for (let d = 1; d <= 182; d++) {
    const time = addDays(lastDate, d);
    if (!isWeekday(time)) continue;
    points.push({
      time,
      lo80: at(d, "lo80"),
      hi80: at(d, "hi80"),
      lo50: at(d, "lo50"),
      hi50: at(d, "hi50"),
      mid: at(d, "mid"),
    });
  }
  return { nodes, points };
}

/** Axis label like v2: "Dec ’25" for months, the year for January. */
export function monthLabel(iso: string): string {
  const d = parse(iso);
  const m = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][
    d.getUTCMonth()
  ];
  return d.getUTCMonth() === 0
    ? String(d.getUTCFullYear())
    : `${m} ’${String(d.getUTCFullYear()).slice(2)}`;
}
