// C-119-2: the budget monitor reports D1 size and the day's reads and writes.
import { expect, it } from "vitest";
import { makeApp } from "../api/src/testkit";

const results = async (signed: Awaited<ReturnType<typeof makeApp>>["signed"]) =>
  (
    (await (await signed("POST", "/api/checks/run")).json()) as {
      results: { id: string; ok: boolean; detail: string }[];
    }
  ).results;

it("C-119-2 monitor reports size, reads and writes as the scheduler sends them", async () => {
  const t = await makeApp({ now: () => new Date("2026-11-28T10:00:00+05:30") });
  expect((await results(t.signed)).find((r) => r.id === "C-119-2")?.ok).toBe(true);
  expect(
    (await t.signed("POST", "/api/monitor", { d1_reads: 1200, d1_writes: 80, build_minutes: 3 }))
      .status,
  ).toBe(200);
  const m = (await (await t.app.request("/api/monitor")).json()) as Record<string, number>;
  expect(m.d1_bytes).toBeGreaterThan(0);
  expect(m).toMatchObject({ d1_reads: 1200, d1_writes: 80, build_minutes: 3, worker_requests: 0 });
  expect((await t.signed("POST", "/api/monitor", { d1_reads: -1 })).status).toBe(200); // bad value ignored
  expect(
    ((await (await t.app.request("/api/monitor")).json()) as Record<string, number>).d1_reads,
  ).toBe(1200);
});
