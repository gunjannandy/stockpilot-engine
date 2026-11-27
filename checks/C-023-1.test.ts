// C-023-1: a row changed between the previous and current run carries a mark; opening it clears it for both people.
import { expect, it } from "vitest";
import { marksRoutes } from "../api/src/marks/routes";
import { testDatasets } from "../api/src/publish/testkit";

it("C-023-1 a changed row is marked, an unchanged one is not, and opening clears it for everyone", async () => {
  const { loadRegistry } = await import("../api/migrate/discover");
  const { SqliteD1 } = await import("../adapters/src/core");
  const { createApp, sign } = await import("../api/src/app");
  const { publishRoutes } = await import("../api/src/publish/routes");
  const { KEY } = await import("../api/src/testkit");
  const db = new SqliteD1();
  const registry = await loadRegistry();
  registry.areas = registry.areas.map((a) =>
    a.name === "publish"
      ? { ...a, routes: (ctx) => publishRoutes(ctx, testDatasets) }
      : a.name === "marks"
        ? { ...a, routes: (ctx) => marksRoutes(ctx, { datasets: testDatasets }) }
        : a,
  );
  const env = { INGEST_HMAC_KEY: KEY, HEALTH_SECRET: "h".repeat(24), SP_ENV: "dev" } as never;
  const app = createApp({ d1: db, env, registry, version: "v1" });
  const post = async (path: string, body: unknown) => {
    const raw = JSON.stringify(body);
    return app.request(path, {
      method: "POST",
      body: raw,
      headers: { "content-type": "application/json", "x-signature": await sign(KEY, raw) },
    });
  };
  const publish = async (run_id: string, rows: unknown[]) => {
    const prov = {
      dataset: "roomy",
      run_id,
      source: "t",
      fetched_at: "2026-11-27T10:00:00+05:30",
      as_of: "2026-11-27",
    };
    expect((await post("/api/publish/rows", { ...prov, rows })).status).toBe(200);
    expect((await post("/api/publish/finish", { dataset: "roomy", run_id })).status).toBe(200);
  };
  const marks = async () =>
    (await app.request("/api/marks")).json() as Promise<{
      items: { key: string; seen: boolean }[];
      unseen: number;
    }>;
  await publish("r1", [
    { id: "a", n: 1 },
    { id: "b", n: 1 },
  ]);
  expect((await marks()).items).toEqual([]); // nothing to compare yet
  await publish("r2", [
    { id: "a", n: 2 },
    { id: "b", n: 1 },
    { id: "c", n: 5 },
  ]);
  const m = await marks();
  expect(m.items.map((i) => i.key).sort()).toEqual(["a", "c"]); // a changed, c is new, b is not marked
  expect(m.unseen).toBe(2);
  const seen = await app.request("/api/marks/seen", {
    method: "POST",
    body: JSON.stringify({ dataset: "roomy", key: "a" }),
    headers: { "content-type": "application/json" },
  });
  expect(seen.status).toBe(200);
  const after = await marks(); // one shared row: the other person sees it cleared too
  expect(after.items.find((i) => i.key === "a")?.seen).toBe(true);
  expect(after.unseen).toBe(1);
  await app.request("/api/marks/seen", {
    method: "POST",
    body: JSON.stringify({ all: true }),
    headers: { "content-type": "application/json" },
  });
  expect((await marks()).unseen).toBe(0);
});
