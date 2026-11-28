// The chart file of one stock, built from its daily rows: prices adjusted for splits and bonuses, and the averages.
// The exchange's own prev_close is already corrected on the ex-date, so close / prev_close is the true daily step; the
// adjusted close is anchored on the latest real close. Volume is left as traded.
import { CHART_MA_DAYS, type ChartResponse, type CloseRow } from "@stockpilot/contract";

const r = (x: number): number =>
  Math.round(x * (Math.abs(x) >= 1 ? 100 : 10000)) / (Math.abs(x) >= 1 ? 100 : 10000);

function mean(close: number[], window: number): (number | null)[] {
  const out: (number | null)[] = [];
  let sum = 0;
  for (let i = 0; i < close.length; i++) {
    sum += close[i] ?? 0;
    if (i >= window) sum -= close[i - window] ?? 0;
    out.push(i >= window - 1 ? r(sum / window) : null);
  }
  return out;
}

export function buildChart(symbol: string, rows: CloseRow[]): ChartResponse {
  const days = [...rows].filter((x) => x.close > 0).sort((a, b) => a.date.localeCompare(b.date));
  const step = days.map((x, i) => {
    if (i === 0) return 1;
    const prev = days[i - 1]?.close ?? 0;
    return x.prev_close && x.prev_close > 0 ? x.close / x.prev_close : x.close / prev;
  });
  const cum: number[] = [];
  step.reduce((acc, s, i) => {
    const next = i === 0 ? 1 : acc * s;
    cum.push(next);
    return next;
  }, 1);
  const lastCum = cum.at(-1) ?? 1;
  const lastClose = days.at(-1)?.close ?? 1;
  const factor = days.map((x, i) => ((cum[i] ?? 1) / lastCum) * (lastClose / x.close));
  const adj = (v: number | null, i: number) => (v === null ? null : r(v * (factor[i] ?? 1)));
  const c = days.map((x, i) => r(x.close * (factor[i] ?? 1)));
  return {
    symbol,
    d: days.map((x) => x.date),
    o: days.map((x, i) => adj(x.open, i)),
    h: days.map((x, i) => adj(x.high, i)),
    l: days.map((x, i) => adj(x.low, i)),
    c,
    v: days.map((x) => x.volume),
    ma2: mean(c, CHART_MA_DAYS.ma2),
    ma10: mean(c, CHART_MA_DAYS.ma10),
  };
}
