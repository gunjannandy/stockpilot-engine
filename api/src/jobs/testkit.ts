// Test helpers for the Job runtime: the real app over SQLite, with the model caps set per test.
import { SqliteD1 } from "../../../adapters/src/core";
import { loadRegistry } from "../../migrate/discover";
import { createApp, type Env, sign } from "../app";
import { KEY } from "../testkit";
import { jobRoutes } from "./routes";

export async function jobsApp(
  opts: { now?: () => Date; caps?: Record<string, number>; env?: Partial<Env> } = {},
) {
  const db = new SqliteD1();
  const registry = await loadRegistry();
  registry.areas = registry.areas.map((a) =>
    a.name === "jobs" ? { ...a, routes: (ctx) => jobRoutes(ctx, { caps: opts.caps }) } : a,
  );
  const env = {
    INGEST_HMAC_KEY: KEY,
    HEALTH_SECRET: "h".repeat(24),
    SP_ENV: "dev",
    ...opts.env,
  } as never;
  const app = createApp({ d1: db, env, registry, version: "v1", now: opts.now });
  const signed = async (method: string, path: string, body?: unknown) => {
    const raw = body === undefined ? "" : JSON.stringify(body);
    return app.request(path, {
      method,
      body: body === undefined ? undefined : raw,
      headers: { "content-type": "application/json", "x-signature": await sign(KEY, raw) },
    });
  };
  const json = (path: string, body: unknown) =>
    app.request(path, {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "content-type": "application/json" },
    });
  return {
    app,
    db,
    signed,
    begin: (body: Record<string, unknown>) => signed("POST", "/api/job/begin", body),
    end: (run_id: string, status: "done" | "failed", error?: string) =>
      signed("POST", "/api/job/end", { run_id, status, error: error ?? null, result: null }),
    pause: (kind: string, paused: boolean) => json("/api/job/pause", { kind, paused }),
    run: async (key: string) =>
      (await (await app.request(`/api/job/run?key=${encodeURIComponent(key)}`)).json()) as {
        retry_at: string | null;
        status: string;
        attempts: number;
      },
    count: async (table: string) =>
      ((await db.prepare(`select count(*) as n from ${table}`).first()) as { n: number }).n,
  };
}
