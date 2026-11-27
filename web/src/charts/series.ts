// Pure chart maths: no DOM, so it is unit-tested. Dates are "YYYY-MM-DD" strings.
export type Bar = { time: string; close: number };
export type Point = { time: string; value: number };
export type RangeId = "6m" | "1y" | "all";

export function sma(bars: Bar[], days: number): Point[] {
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

export function rangeStart(last: string, range: RangeId, first: string): string {
  if (range === "all") return first;
  const d = new Date(`${last}T00:00:00Z`);
  d.setUTCMonth(d.getUTCMonth() - (range === "6m" ? 6 : 12));
  const s = d.toISOString().slice(0, 10);
  return s < first ? first : s;
}

/** Zoom factor for one wheel notch; null means plain scroll, which never zooms. */
export function wheelZoom(e: {
  ctrlKey: boolean;
  metaKey: boolean;
  deltaY: number;
}): number | null {
  if (!e.ctrlKey && !e.metaKey) return null;
  return e.deltaY < 0 ? 1.15 : 1 / 1.15;
}

/** Forecast band: widens with the square root of days ahead. */
export function band(last: number, days: number, vol: number, step: number) {
  const out: { time: number; lo: number; hi: number; mid: number }[] = [];
  for (let d = step; d <= days; d += step) {
    const w = last * vol * Math.sqrt(d);
    out.push({ time: d, lo: +(last - w).toFixed(2), hi: +(last + w).toFixed(2), mid: last });
  }
  return out;
}
