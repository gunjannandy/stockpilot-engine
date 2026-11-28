// C-103-1: a paused Job kind starts no Job.
import { expect, it } from "vitest";
import { scheduleApp } from "../api/src/schedule/testkit";

const put = (t: Awaited<ReturnType<typeof scheduleApp>>, b: unknown) =>
  t.app.request("/api/admin/job-pause", {
    method: "PUT",
    body: JSON.stringify(b),
    headers: { "content-type": "application/json" },
  });

it("C-103-1 a paused kind refuses begin and press; other kinds run; resume restores it", async () => {
  const t = await scheduleApp({ datasets: [], now: () => new Date("2026-11-26T10:00:00+05:30") });
  expect((await put(t, { kind: "analyse", paused: true })).status).toBe(200);
  expect((await t.begin({ kind: "analyse", run_id: "r1" })).status).toBe(423);
  expect((await t.press({ kind: "analyse", subject: "ABC" })).status).toBe(423);
  expect(t.github.dispatched).toHaveLength(0);
  expect((await t.begin({ kind: "ping", run_id: "r2" })).status).toBe(200);
  const state = (await (await t.app.request("/api/admin/state")).json()) as {
    paused_kinds: string[];
  };
  expect(state.paused_kinds).toEqual(["analyse"]);
  await put(t, { kind: "analyse", paused: false });
  expect((await t.begin({ kind: "analyse", run_id: "r3" })).status).toBe(200);
});
