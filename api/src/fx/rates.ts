// USD/INR source for `rateOn`: stored daily rates, filled from the free Frankfurter feed (ECB reference rates, no key).
// Read endpoints only; nothing here touches a broker.
import { addDays, type Day } from "../../../money/src/core/dates";
import type { RateOn } from "../../../money/src/lots/types";
import type { D1Like } from "../app";

type Fetcher = (url: string) => Promise<{ ok: boolean; json: () => Promise<unknown> }>;
const FEED = "https://api.frankfurter.app";

/** Rate on or before a day (weekends and holidays take the last published rate). Null before the first stored day. */
export async function loadRateOn(d1: D1Like): Promise<RateOn> {
  const rows =
    (
      (await d1.prepare("select day, usd_inr from fx_rates order by day").all()) as {
        results?: { day: string; usd_inr: number }[];
      }
    ).results ?? [];
  if (rows.length === 0) return null;
  return (day: Day) => {
    let lo = 0;
    let hi = rows.length - 1;
    let found: number | null = null;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      const r = rows[mid] as { day: string; usd_inr: number };
      if (r.day <= day) {
        found = r.usd_inr;
        lo = mid + 1;
      } else hi = mid - 1;
    }
    return found;
  };
}

/** Fetch USD/INR for from..to (inclusive). Returns day -> rate; empty on any failure. */
export async function fetchUsdInr(
  from: Day,
  to: Day,
  fetcher: Fetcher = (u) => fetch(u),
): Promise<Record<Day, number>> {
  try {
    const res = await fetcher(`${FEED}/${from}..${to}?from=USD&to=INR`);
    if (!res.ok) return {};
    const body = (await res.json()) as { rates?: Record<string, { INR?: number }> };
    const out: Record<Day, number> = {};
    for (const [d, v] of Object.entries(body.rates ?? {}))
      if (typeof v?.INR === "number" && v.INR > 0) out[d] = v.INR;
    return out;
  } catch {
    return {};
  }
}

/** Fill the gap from the day after the last stored rate (or `since`) up to `today`. Best effort: returns rows added. */
export async function refreshRates(
  d1: D1Like,
  today: Day,
  since: Day,
  fetcher?: Fetcher,
): Promise<number> {
  const last = (
    (await d1.prepare("select max(day) as d from fx_rates").all()) as {
      results?: { d: string | null }[];
    }
  ).results?.[0]?.d;
  const from = last ? addDays(last, 1) : since;
  if (from > today) return 0;
  const got = await fetchUsdInr(from, today, fetcher);
  let n = 0;
  for (const [day, r] of Object.entries(got)) {
    await d1
      .prepare("insert or ignore into fx_rates (day, usd_inr) values (?, ?)")
      .bind(day, r)
      .run();
    n++;
  }
  return n;
}
