/** Fund detail numbers worked out in the browser from a fund's weekly NAVs (`fundNavs`). Pure, no data of anyone's own. */

type Nav = [string, number];

/** Return for each calendar year with a NAV at the previous year end (or within 10 days of it), percent.
 * The latest year is part-way through: `partial` is true for it. Oldest first. */
export function calendarReturns(navs: Nav[]): { year: number; ret: number; partial: boolean }[] {
  const lastOf = new Map<number, Nav>();
  for (const n of navs) lastOf.set(Number(n[0].slice(0, 4)), n);
  const years = [...lastOf.keys()].sort((a, b) => a - b);
  const out: { year: number; ret: number; partial: boolean }[] = [];
  for (const y of years) {
    const prev = lastOf.get(y - 1);
    const cur = lastOf.get(y);
    if (!prev || !cur || prev[1] <= 0) continue;
    const gap = (Date.parse(`${y - 1}-12-31`) - Date.parse(prev[0])) / 86_400_000;
    if (gap > 10) continue;
    out.push({
      year: y,
      ret: Math.round((cur[1] / prev[1] - 1) * 10_000) / 100,
      partial: y === years[years.length - 1] && cur[0] < `${y}-12-24`,
    });
  }
  return out;
}

/** Yearly return (percent) of putting the same sum in on the first NAV of each month for `months` months and
 * holding to the last NAV. Null when the history is shorter than `months` (default 36) or has no NAV in a month. */
export function sipReturn(navs: Nav[], months = 36): number | null {
  if (navs.length < 2 || months < 12) return null;
  const [lastDay, lastNav] = navs[navs.length - 1] as Nav;
  const ym = (s: string) => Number(s.slice(0, 4)) * 12 + Number(s.slice(5, 7)) - 1;
  const endM = ym(lastDay);
  const firstOfMonth = new Map<number, Nav>();
  for (const n of navs) if (!firstOfMonth.has(ym(n[0]))) firstOfMonth.set(ym(n[0]), n);
  const flows: { t: number; amt: number }[] = [];
  let units = 0;
  for (let m = endM - months + 1; m <= endM; m++) {
    const n = firstOfMonth.get(m);
    if (!n || n[1] <= 0) return null;
    units += 1 / n[1];
    flows.push({ t: Date.parse(n[0]) / 86_400_000, amt: -1 });
  }
  if (Date.parse(`${firstOfMonth.get(endM - months + 1)?.[0]}`) > Date.parse(lastDay)) return null;
  flows.push({ t: Date.parse(lastDay) / 86_400_000, amt: units * lastNav });
  const t0 = (flows[0] as { t: number }).t;
  const npv = (r: number) => flows.reduce((s, f) => s + f.amt / (1 + r) ** ((f.t - t0) / 365), 0);
  let lo = -0.99;
  let hi = 10;
  if (npv(lo) * npv(hi) > 0) return null;
  for (let i = 0; i < 200; i++) {
    const mid = (lo + hi) / 2;
    if (npv(lo) * npv(mid) <= 0) hi = mid;
    else lo = mid;
  }
  return Math.round(((lo + hi) / 2) * 10_000) / 100;
}
