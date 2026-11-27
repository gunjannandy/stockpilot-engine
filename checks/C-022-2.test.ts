// C-022-2: the app applies pending expand migrations before serving its first request on a new version.
import { describe, expect, it } from "vitest";
import { SqliteD1 } from "../adapters/src/core";
import { loadRegistry } from "../api/migrate/discover";
import { createApp } from "../api/src/app";
import { makeApp } from "../api/src/testkit";

describe("C-022-2 migrate before the first request", () => {
  it("serves the first request on an empty database by migrating first", async () => {
    const { app, db } = await makeApp();
    const res = await app.request("/api/ping");
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ latest: null, count: 0 });
    const done = (await db.prepare("select name from d1_migrations").all()).results;
    expect(done.length).toBeGreaterThanOrEqual(5);
  });

  it("applies a migration shipped by a new version before that version's first request", async () => {
    const db = new SqliteD1();
    const registry = await loadRegistry();
    await createApp({ d1: db, env: {}, registry, version: "v1" }).request("/api/ping");
    const next = {
      ...registry,
      migrations: [
        ...registry.migrations,
        { name: "29990101000000_extra.sql", sql: "create table extra (x text);" },
      ],
    };
    const app2 = createApp({ d1: db, env: {}, registry: next, version: "v2" });
    await app2.request("/api/ping");
    const t = await db.prepare("select name from sqlite_master where name = 'extra'").all();
    expect(t.results).toHaveLength(1);
  });

  it("answers 'updating' and serves nothing when a pending step is not expand-only", async () => {
    const db = new SqliteD1();
    const registry = await loadRegistry();
    const bad = {
      ...registry,
      migrations: [
        ...registry.migrations,
        { name: "29990101000000_bad.sql", sql: "drop table ping;" },
      ],
    };
    const res = await createApp({ d1: db, env: {}, registry: bad, version: "v3" }).request(
      "/api/ping",
    );
    expect(res.status).toBe(503);
  });
});
