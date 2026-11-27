// The three promises (decisions §6), measured and stored once a day:
// the site is up; data has the last trading day's close by 08:30 IST; Analyse answers within 5 minutes.
import { istDay, istText } from "../app";
import { expectedAsOf } from "../calendar/calendar";
import { loadCalendar } from "../calendar/routes";
import type { Core } from "../jobs/runtime";

export const PROMISES = ["site_up", "data_fresh", "analyse_fast"] as const;
export type PromiseName = (typeof PROMISES)[number];
export const ANALYSE_LIMIT_MS = 5 * 60_000;

type Outcome = { ok: boolean; detail: string };

export async function measurePromises(
  c: Core,
  opts: { siteUrl?: string; fetch?: typeof fetch } = {},
): Promise<Record<PromiseName, Outcome>> {
  const f = opts.fetch ?? fetch;
  let site: Outcome;
  if (!opts.siteUrl) site = { ok: true, detail: "answering this request" };
  else
    try {
      const r = await f(`${opts.siteUrl}/api/ping`);
      site = { ok: r.ok, detail: `ping answered ${r.status}` };
    } catch (e) {
      site = { ok: false, detail: `ping failed: ${e instanceof Error ? e.message : e}` };
    }

  // Fresh means the last trading day's close is in: any current dataset at or past that day.
  const cal = await loadCalendar({ d1: c.d1 });
  const want = expectedAsOf(cal, c.now());
  const p = (await c.d1
    .prepare("select max(as_of) as m from pointers where dataset != 'calendar'")
    .first()) as {
    m: string | null;
  } | null;
  const have = p?.m ?? null;
  const fresh: Outcome = have
    ? { ok: have >= want, detail: `latest data ${have}, want ${want}` }
    : { ok: false, detail: "no data published yet" };

  const day = istDay(c.now());
  const a = (await c.d1
    .prepare(
      "select duration_ms, status from job_runs where kind = 'analyse' and day = ? and status in ('done','failed')",
    )
    .bind(day)
    .all()) as { results: { duration_ms: number | null; status: string }[] };
  const slow = a.results.filter(
    (r) => r.status === "failed" || (r.duration_ms ?? 0) > ANALYSE_LIMIT_MS,
  );
  const analyse: Outcome = {
    ok: slow.length === 0,
    detail: a.results.length
      ? `${a.results.length} runs, ${slow.length} slow or failed`
      : "no Analyse runs today",
  };
  return { site_up: site, data_fresh: fresh, analyse_fast: analyse };
}

/** Store today's results; each (day, promise) is written once per call, the latest measure wins. */
export async function storePromises(c: Core, opts?: Parameters<typeof measurePromises>[1]) {
  const results = await measurePromises(c, opts);
  const day = istDay(c.now());
  const at = istText(c.now());
  for (const name of PROMISES) {
    const r = results[name];
    await c.d1
      .prepare(
        `insert into promise_results (day, promise, ok, detail, at) values (?, ?, ?, ?, ?)
         on conflict(day, promise) do update set ok = excluded.ok, detail = excluded.detail, at = excluded.at`,
      )
      .bind(day, name, r.ok ? 1 : 0, r.detail, at)
      .run();
  }
  return results;
}
