// C-123-1: the three promises are measured and stored daily, one row per promise per day.
import { expect, it } from "vitest";
import { PROMISES, storePromises } from "../api/src/promises/promises";
import { opsApp } from "../api/src/watcher/testkit";

it("C-123-1 promise results are stored daily, once per promise per day", async () => {
  const t = await opsApp();
  await storePromises(t.core());
  await storePromises(t.core());
  const rows = (await t.db.prepare("select * from promise_results order by promise").all()) as {
    results: { promise: string; day: string; ok: number }[];
  };
  expect(rows.results.map((r) => r.promise).sort()).toEqual([...PROMISES].sort());
  const next = new Date(t.now.getTime() + 24 * 3600_000);
  await storePromises(t.core(next));
  const all = (await t.db.prepare("select count(*) as n from promise_results").first()) as {
    n: number;
  };
  expect(all.n).toBe(6);
});

it("C-123-1 a site that does not answer fails the promise", async () => {
  const t = await opsApp();
  const down = (async () => new Response("no", { status: 503 })) as unknown as typeof fetch;
  const r = await storePromises(t.core(), { siteUrl: "https://x.test", fetch: down });
  expect(r.site_up.ok).toBe(false);
  expect(r.data_fresh.ok).toBe(false);
});
