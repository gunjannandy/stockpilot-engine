// Test helpers for the publishing checks: the real app over SQLite with the publish and data areas
// pointed at small test datasets (a tiny write budget, a file dataset, row and run checks).
import type { Dataset } from "@stockpilot/contract";
import { z } from "zod";
import { SqliteD1 } from "../../../adapters/src/core";
import { loadRegistry } from "../../migrate/discover";
import { createApp, sign } from "../app";
import { dataRoutes } from "../data/routes";
import { KEY } from "../testkit";
import { type Datasets, defaultDatasets } from "./lib";
import { publishRoutes } from "./routes";

export const Item = z.object({ id: z.string().min(1), n: z.number() });

const base = {
  job: "ping",
  table: "ping",
  schedule: "in tests",
  freshnessHours: 24,
  recomputable: true,
} as const;

export const testDatasets: Datasets = {
  ...defaultDatasets,
  small: {
    ...base,
    name: "small",
    checks: { row: ["id is not empty", "n is not negative"], run: ["at least two rows"] },
    writeBudget: 50,
    row: Item,
    rowCheck: (r) => ((r.n as number) < 0 ? "n is negative" : null),
    runCheck: (run) => (run.rowCount < 2 ? "fewer than two rows" : null),
  },
  tiny: {
    ...base,
    name: "tiny",
    checks: { row: ["id is not empty"], run: [] },
    writeBudget: 5,
    row: Item,
  },
  roomy: { ...base, name: "roomy", checks: { row: ["id"], run: [] }, writeBudget: 5000, row: Item },
  wide: {
    ...base,
    name: "wide",
    checks: { row: [], run: [] },
    writeBudget: 5000,
    rowsLimit: 1500,
    row: Item,
  },
  big: {
    ...base,
    name: "big",
    checks: { row: [], run: ["at least two rows"] },
    writeBudget: 10,
    row: Item,
    delivery: "file",
    runCheck: (run) => (run.rowCount < 2 ? "too few rows" : null),
  },
} satisfies Record<string, Dataset>;

export async function publishApp(opts: { now?: () => Date; fetch?: typeof fetch } = {}) {
  const db = new SqliteD1();
  const sql: string[] = [];
  const prepare = db.prepare.bind(db);
  db.prepare = (text: string) => {
    sql.push(text);
    return prepare(text);
  };
  const registry = await loadRegistry();
  registry.areas = registry.areas.map((a) =>
    a.name === "publish"
      ? { ...a, routes: (ctx) => publishRoutes(ctx, testDatasets) }
      : a.name === "data"
        ? { ...a, routes: (ctx) => dataRoutes(ctx, { datasets: testDatasets, fetch: opts.fetch }) }
        : a,
  );
  const env = { INGEST_HMAC_KEY: KEY, HEALTH_SECRET: "h".repeat(24), SP_ENV: "dev" } as never;
  const app = createApp({ d1: db, env, registry, version: "v1", now: opts.now });
  const signed = async (path: string, body: unknown) => {
    const raw = JSON.stringify(body);
    return app.request(path, {
      method: "POST",
      body: raw,
      headers: { "content-type": "application/json", "x-signature": await sign(KEY, raw) },
    });
  };
  const prov = (dataset: string, run_id: string, as_of = "2026-11-27") => ({
    dataset,
    run_id,
    source: "test",
    fetched_at: "2026-11-27T10:00:00+05:30",
    as_of,
  });
  const rows = (dataset: string, run_id: string, rs: unknown[], as_of?: string) =>
    signed("/api/publish/rows", { ...prov(dataset, run_id, as_of), rows: rs });
  const finish = (dataset: string, run_id: string, extra: object = {}) =>
    signed("/api/publish/finish", { dataset, run_id, ...extra });
  const read = (dataset: string, headers: Record<string, string> = {}) =>
    app.request(`/api/data/${dataset}`, { headers });
  return { app, db, rows, finish, read, signed, prov, sql };
}
export const items = (n: number, from = 0) =>
  Array.from({ length: n }, (_, i) => ({ id: `r${from + i}`, n: from + i }));
