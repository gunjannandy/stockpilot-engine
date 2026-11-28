import { HealthResponse, JobKind } from "@stockpilot/contract";
import { expect, it } from "vitest";
import { HEALTH, makeApp } from "../testkit";

it("Backup reports: signed writes only, the latest of each kind shows, bad bodies are refused", async () => {
  const { app, signed } = await makeApp();
  const body = {
    kind: "backup",
    ok: true,
    detail: "2 tables",
    tables: { calls: { rows: 3, sha256: "x" } },
  };
  expect(
    (await app.request("/api/backup", { method: "POST", body: JSON.stringify(body) })).status,
  ).toBe(401);
  expect((await signed("POST", "/api/backup", { ...body, kind: "other" })).status).toBe(400);
  expect((await signed("POST", "/api/backup", { ...body, tables: [] })).status).toBe(400);
  expect((await signed("POST", "/api/backup", { ...body, ok: "yes" })).status).toBe(400);
  expect((await signed("POST", "/api/backup", body)).status).toBe(200);
  expect(
    (
      await signed("POST", "/api/backup", {
        ...body,
        kind: "drill",
        ok: false,
        detail: "calls differs",
      })
    ).status,
  ).toBe(200);
  const got = (await (await app.request("/api/backup")).json()) as Record<
    string,
    { ok: boolean; tables: unknown } | null
  >;
  expect(got.backup?.ok).toBe(true);
  expect(got.backup?.tables).toEqual(body.tables);
  expect(got.drill?.ok).toBe(false);
});

it("Backup reports: nothing yet reads as null, and only the last 60 of a kind are kept", async () => {
  const { app, signed, db } = await makeApp();
  expect(await (await app.request("/api/backup")).json()).toEqual({ backup: null, drill: null });
  for (let i = 0; i < 62; i++)
    await signed("POST", "/api/backup", { kind: "backup", ok: true, detail: `n${i}`, tables: {} });
  const n = await db.prepare("select count(*) as n from backup_reports").first();
  expect((n as { n: number }).n).toBe(60);
});

it("Health shows the latest backup and drill, and the drill is a Job kind", async () => {
  const { app, signed } = await makeApp();
  const health = async () =>
    HealthResponse.parse(
      await (await app.request("/api/health", { headers: { "x-health-secret": HEALTH } })).json(),
    );
  expect((await health()).backup).toEqual({ backup: null, drill: null });
  await signed("POST", "/api/backup", {
    kind: "drill",
    ok: true,
    detail: "2 tables match",
    tables: {},
  });
  const got = (await health()).backup;
  expect(got.backup).toBeNull();
  expect(got.drill?.ok).toBe(true);
  expect(got.drill?.detail).toBe("2 tables match");
  expect(JobKind.safeParse("drill").success).toBe(true);
});

it("Health lists the latest promises and dependency results", async () => {
  const { app, db } = await makeApp();
  const get = async () =>
    HealthResponse.parse(
      await (await app.request("/api/health", { headers: { "x-health-secret": HEALTH } })).json(),
    );
  const empty = await get();
  expect(empty.promises).toEqual([]);
  expect(empty.dependencies).toEqual([]);
  const at = "2026-11-28T08:00:00+05:30";
  for (const [day, ok] of [
    ["2026-11-27", false],
    ["2026-11-28", true],
  ] as const)
    await db
      .prepare(
        "insert into promise_results (day, promise, ok, detail, at) values (?, 'site_up', ?, 'd', ?)",
      )
      .bind(day, ok ? 1 : 0, at)
      .run();
  await db
    .prepare(
      "insert into dep_checks (dep, ok, detail, fallback, at) values ('nse', 0, 'answered 503', 'use last data', ?)",
    )
    .bind(at)
    .run();
  const got = await get();
  expect(got.promises).toEqual([
    { promise: "site_up", day: "2026-11-28", ok: true, detail: "d", at },
  ]);
  expect(got.dependencies[0]).toMatchObject({ dep: "nse", ok: false, fallback: "use last data" });
});
