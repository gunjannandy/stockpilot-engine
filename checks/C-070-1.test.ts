// C-070-1: the Kite callback stores raw holdings and trades and reports the count of changes.
// Also guards the rule that Kite is only ever read: no order path in the adapter source.
import { readFileSync } from "node:fs";
import { expect, it } from "vitest";
import { fakeKite, READ_PATHS } from "../adapters/src/kite";
import { loadRegistry } from "../api/migrate/discover";
import { createApp } from "../api/src/app";
import { kiteRoutes } from "../api/src/kite/routes";
import { makeApp } from "../api/src/testkit";

async function appWith(kite = fakeKite()) {
  const t = await makeApp();
  // Route under test, mounted on the same database with the fake Kite.
  const reg = await loadRegistry();
  const base = createApp({
    d1: t.db,
    env: t.env,
    registry: {
      ...reg,
      areas: reg.areas
        .filter((a) => a.name !== "kite")
        .concat([{ name: "kite-test", routes: (ctx) => kiteRoutes(ctx, { kite }) }]),
    },
    now: () => new Date("2026-11-28T03:30:00Z"),
  });
  return { app: base, db: t.db };
}

it("C-070-1 the callback stores raw holdings and trades and reports the changes", async () => {
  const { app, db } = await appWith();
  const res = await app.request("/kite/callback?request_token=abc&status=success");
  expect(res.status).toBe(302);
  expect(res.headers.get("location")).toBe("/sync?synced=1&changes=3");
  const h = (await db
    .prepare("select count(*) as n from holdings where account = 'primary' and source = 'kite'")
    .first()) as { n: number };
  const tr = (await db
    .prepare("select count(*) as n from trades where source = 'kite'")
    .first()) as { n: number };
  expect(h.n).toBe(2);
  expect(tr.n).toBe(1);
  const status = (await (await app.request("/api/sync")).json()) as {
    changes: number;
    steps: unknown[];
  };
  expect(status.changes).toBe(3);
  expect(status.steps).toHaveLength(4);
});

it("C-070-1 a second sync with nothing new reports no changes", async () => {
  const { app } = await appWith();
  await app.request("/kite/callback?request_token=abc&status=success");
  const again = await app.request("/kite/callback?request_token=abc&status=success");
  expect(again.headers.get("location")).toBe("/sync?synced=1&changes=0");
});

it("C-070-1 a refused login stores nothing", async () => {
  const { app, db } = await appWith(fakeKite({}, { refuse: true }));
  expect((await app.request("/kite/callback?request_token=abc")).status).toBe(502);
  expect((await app.request("/kite/callback?status=error")).status).toBe(400);
  const h = (await db.prepare("select count(*) as n from holdings").first()) as { n: number };
  expect(h.n).toBe(0);
});

it("C-070-1 Kite is only read: the adapter names no order path", () => {
  const src = readFileSync(new URL("../adapters/src/kite/index.ts", import.meta.url), "utf8");
  expect(Object.values(READ_PATHS).every((p) => !/order/i.test(p))).toBe(true);
  expect(src).not.toMatch(/\/orders|method:\s*"(PUT|DELETE)"/);
});
