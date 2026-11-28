// C-105-1: Recompute last N days starts one Job with that range.
import { expect, it } from "vitest";
import { SqliteD1 } from "../adapters/src/core";
import { fakeGithub } from "../adapters/src/github";
import { loadRegistry } from "../api/migrate/discover";
import { adminRoutes } from "../api/src/adminctl/routes";
import { createApp } from "../api/src/app";
import { KEY } from "../api/src/testkit";

async function scheduleApp(_o: unknown) {
  const github = fakeGithub({});
  const registry = await loadRegistry();
  registry.areas = registry.areas.map((a) =>
    a.name === "adminctl" ? { ...a, routes: (ctx) => adminRoutes(ctx, { github }) } : a,
  );
  const app = createApp({
    d1: new SqliteD1(),
    env: { INGEST_HMAC_KEY: KEY, HEALTH_SECRET: "h".repeat(24), SP_ENV: "dev" } as never,
    registry,
    version: "v1",
    now: () => new Date("2026-11-26T10:00:00+05:30"),
  });
  await app.request("/api/ping");
  return { app, github };
}
type T = Awaited<ReturnType<typeof scheduleApp>>;
const post = (t: T, b: unknown) =>
  t.app.request("/api/admin/recompute", {
    method: "POST",
    body: JSON.stringify(b),
    headers: { "content-type": "application/json" },
  });

it("C-105-1 one Job, today minus N-1 days to today", async () => {
  const t = await scheduleApp({ datasets: [], now: () => new Date("2026-11-26T10:00:00+05:30") });
  const res = await post(t, { dataset: "calendar", days: 5 });
  expect(res.status).toBe(200);
  expect(await res.json()).toMatchObject({
    status: "queued",
    range: { from: "2026-11-22", to: "2026-11-26" },
  });
  expect(t.github.dispatched).toHaveLength(1);
  expect(t.github.dispatched[0]?.inputs).toMatchObject({
    kind: "calendar",
    from: "2026-11-22",
    to: "2026-11-26",
  });
});
it("C-105-1 refuses an unknown or non-recomputable dataset, a bad N, and a paused kind", async () => {
  const t = await scheduleApp({ datasets: [], now: () => new Date("2026-11-26T10:00:00+05:30") });
  expect((await post(t, { dataset: "nope", days: 3 })).status).toBe(404);
  expect((await post(t, { dataset: "ping", days: 3 })).status).toBe(400);
  expect((await post(t, { dataset: "calendar", days: 0 })).status).toBe(400);
  await t.app.request("/api/admin/job-pause", {
    method: "PUT",
    body: JSON.stringify({ kind: "calendar", paused: true }),
    headers: { "content-type": "application/json" },
  });
  expect((await post(t, { dataset: "calendar", days: 3 })).status).toBe(423);
  expect(t.github.dispatched).toHaveLength(0);
});
