// C-115-1: rerunning a Job for the same range leaves the same rows.
import { expect, it } from "vitest";
import { jobsApp } from "../api/src/jobs/testkit";

const prov = (run_id: string) => ({
  dataset: "calendar",
  run_id,
  source: "test",
  fetched_at: "2026-11-27T08:55:00+05:30",
  as_of: "2026-11-27",
});
const holiday = (n: number) => ({
  id: `h-${n}`,
  kind: "holiday",
  date: `2026-12-${String(n).padStart(2, "0")}`,
  reason: "Holiday",
  symbol: null,
  old_shares: null,
  new_shares: null,
  new_symbol: null,
});

it("C-115-1 a Job takes a date range and a rerun of the range is allowed and leaves the same rows", async () => {
  const t = await jobsApp();
  const rows = [holiday(25), holiday(26)];
  const runOnce = async (run_id: string, rerun: boolean) => {
    const b = await t.begin({ kind: "calendar", run_id, from: "2026-11-20", to: "2026-11-27", rerun });
    expect(b.status).toBe(200);
    expect(((await b.json()) as { range: unknown }).range).toEqual({ from: "2026-11-20", to: "2026-11-27" });
    expect((await t.signed("POST", "/api/publish/rows", { ...prov(run_id), rows })).status).toBe(200);
    await t.signed("POST", "/api/publish/finish", { dataset: "calendar", run_id });
    await t.end(run_id, "done");
    const res = await t.app.request("/api/data/calendar");
    return (await res.json()) as { run_id: string; rows: unknown[] };
  };
  const first = await runOnce("a1", false);
  // Without rerun the same day's Job is refused; Admin's Recompute reruns it.
  expect((await t.begin({ kind: "calendar", run_id: "a2" })).status).toBe(409);
  const second = await runOnce("a2", true);
  expect(second.run_id).toBe("a2");
  expect(second.rows).toEqual(first.rows);
  expect(second.rows).toHaveLength(2);
  expect(await t.count("job_runs")).toBe(1);
});

it("C-115-1 a range that ends before it starts is refused", async () => {
  const t = await jobsApp();
  const b = await t.begin({ kind: "calendar", run_id: "x", from: "2026-11-27", to: "2026-11-20" });
  expect(b.status).toBe(400);
});
