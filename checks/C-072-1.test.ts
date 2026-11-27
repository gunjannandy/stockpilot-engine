// C-072-1: Refresh starts the documents workflow (private repo) and keys the run, one per day.
import { expect, it } from "vitest";
import { fakeGithub } from "../adapters/src/github";
import { loadRegistry } from "../api/migrate/discover";
import { createApp } from "../api/src/app";
import { kiteRoutes } from "../api/src/kite/routes";
import { makeApp } from "../api/src/testkit";

async function appWith(live: boolean) {
  const t = await makeApp();
  const github = fakeGithub();
  const reg = await loadRegistry();
  const api = createApp({
    d1: t.db,
    env: { ...t.env, ...(live ? { DOCUMENTS_LIVE: "1" } : {}) },
    registry: {
      ...reg,
      areas: reg.areas
        .filter((a) => a.name !== "kite")
        .concat([{ name: "kite-test", routes: (ctx) => kiteRoutes(ctx, { github }) }]),
    },
    now: () => new Date("2026-11-28T03:30:00Z"),
  });
  return { app: api, github, db: t.db };
}

it("C-072-1 Refresh dispatches documents.yml in the private repo and keys the run", async () => {
  const { app, github, db } = await appWith(true);
  const res = await app.request("/api/refresh", { method: "POST" });
  expect(res.status).toBe(200);
  expect(github.dispatched).toHaveLength(1);
  expect(github.dispatched[0]).toMatchObject({
    repo: "stockpilot-hq/stockpilot",
    workflow: "documents.yml",
  });
  const row = (await db
    .prepare("select status from job_runs where key = 'documents|drive|2026-11-28'")
    .first()) as { status: string };
  expect(row.status).toBe("queued");
  // pressed again while queued: no second run
  expect((await app.request("/api/refresh", { method: "POST" })).status).toBe(409);
  expect(github.dispatched).toHaveLength(1);
});

it("C-072-1 until cutover nothing is started", async () => {
  const { app, github } = await appWith(false);
  expect((await app.request("/api/refresh", { method: "POST" })).status).toBe(503);
  expect(github.dispatched).toHaveLength(0);
});
