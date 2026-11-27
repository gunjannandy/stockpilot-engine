import { expect, it } from "vitest";
import { makeApp } from "../testkit";

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
