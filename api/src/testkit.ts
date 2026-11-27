// Test helpers: the real app over an in-memory SQLite D1, signed calls as a Job would make them.
import { SqliteD1 } from "../../adapters/src/core";
import { loadRegistry } from "../migrate/discover";
import { createApp, type Env, sign } from "./app";

export const KEY = "k".repeat(40);
export const HEALTH = "h".repeat(24);

export async function makeApp(
  opts: { version?: string; now?: () => Date; env?: Env; db?: SqliteD1 } = {},
) {
  const db = opts.db ?? new SqliteD1();
  // SP_ENV=dev: sign-in lets everyone in as the owner (api/src/auth); the sign-in checks build their own app.
  const env: Env = {
    INGEST_HMAC_KEY: KEY,
    HEALTH_SECRET: HEALTH,
    SP_ENV: "dev",
    ...opts.env,
  } as Env;
  const registry = await loadRegistry();
  const app = createApp({ d1: db, env, registry, version: opts.version ?? "v1", now: opts.now });
  const signed = async (method: string, path: string, body?: unknown) => {
    const raw = body === undefined ? "" : JSON.stringify(body);
    return app.request(path, {
      method,
      body: body === undefined ? undefined : raw,
      headers: { "content-type": "application/json", "x-signature": await sign(KEY, raw) },
    });
  };
  const withSecret = (path: string, init: RequestInit = {}) =>
    app.request(path, { ...init, headers: { ...init.headers, "x-health-secret": HEALTH } });
  return { app, db, env, registry, signed, withSecret };
}
