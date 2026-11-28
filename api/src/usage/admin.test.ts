import { AdminOverview } from "@stockpilot/contract";
import { expect, it } from "vitest";
import { makeApp } from "../testkit";

it("admin overview parses, try again requeues a failed Job, a click writes one count", async () => {
  const { app, db } = await makeApp();
  await app.request("/api/admin"); // boots migrations
  await db
    .prepare(
      "insert into job_runs (key, kind, subject, day, status, range_from, range_to, attempts, error, started_at, finished_at) values ('ping|all|2026-11-28','ping','all','2026-11-28','failed','2026-11-28','2026-11-28',1,'boom','2026-11-28T09:00:00+05:30','2026-11-28T09:01:00+05:30')",
    )
    .run();
  const o = AdminOverview.parse(await (await app.request("/api/admin")).json());
  expect(o.runs[0]?.status).toBe("failed");
  expect(o.needs_you.length).toBeGreaterThan(0);
  const r = await app.request("/api/admin/retry", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ key: "ping|all|2026-11-28" }),
  });
  expect(r.status).toBe(200);
  expect(AdminOverview.parse(await (await app.request("/api/admin")).json()).runs[0]?.status).toBe(
    "queued",
  );
  for (let i = 0; i < 2; i++)
    await app.request("/api/usage", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ screen: "admin", button: "x" }),
    });
  expect(AdminOverview.parse(await (await app.request("/api/admin")).json()).usage[0]?.n).toBe(2);
});

it("a received ask shows in Needs you", async () => {
  const { app, db } = await makeApp();
  await app.request("/api/admin");
  await db
    .prepare(
      "insert into feedback (id, text, status, created_at, updated_at) values ('fb-1','make it bigger','received','2026-11-28T09:00:00+05:30','2026-11-28T09:00:00+05:30')",
    )
    .run();
  const o = AdminOverview.parse(await (await app.request("/api/admin")).json());
  expect(o.needs_you.some((n) => n.kind === "feedback")).toBe(true);
});
