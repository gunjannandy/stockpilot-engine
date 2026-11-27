// C-113-1: the ingest door rejects rows without source, fetch time and as of.
import { expect, it } from "vitest";
import { items, publishApp } from "../api/src/publish/testkit";

it("C-113-1 rows without source, fetched_at or as_of are rejected and nothing is written", async () => {
  const t = await publishApp();
  const full = { ...t.prov("roomy", "a"), rows: items(2) };
  for (const field of ["source", "fetched_at", "as_of", "run_id"] as const) {
    const body: Record<string, unknown> = { ...full };
    delete body[field];
    const res = await t.signed("/api/publish/rows", body);
    expect(res.status, field).toBe(400);
    expect(((await res.json()) as { error: string }).error, field).toContain(field);
  }
  const bad = await t.signed("/api/publish/rows", { ...full, fetched_at: "yesterday" });
  expect(bad.status).toBe(400);
  expect(
    ((await t.db.prepare("select count(*) as n from dataset_rows").first()) as { n: number }).n,
  ).toBe(0);
  expect(((await t.db.prepare("select count(*) as n from runs").first()) as { n: number }).n).toBe(
    0,
  );
  expect((await t.signed("/api/publish/rows", full)).status).toBe(200);
});

it("C-113-1 the door takes only signed calls", async () => {
  const t = await publishApp();
  const res = await t.app.request("/api/publish/rows", { method: "POST", body: "{}" });
  expect(res.status).toBe(401);
});
