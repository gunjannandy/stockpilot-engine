// Test helpers for operations: the real app over SQLite (which applies every migration), a fake bot, a clock.
import { SqliteD1 } from "../../../adapters/src/core";
import { fakeGithub } from "../../../adapters/src/github";
import { loadRegistry } from "../../migrate/discover";
import { createApp, istText } from "../app";
import type { Core } from "../jobs/runtime";

export async function opsApp() {
  const db = new SqliteD1();
  const now = new Date("2026-11-27T04:00:00Z");
  const github = fakeGithub();
  const env = {
    INGEST_HMAC_KEY: "k".repeat(40),
    HEALTH_SECRET: "h".repeat(24),
    SP_ENV: "dev",
  } as never;
  const app = createApp({
    d1: db,
    env,
    registry: await loadRegistry(),
    version: "v1",
    now: () => now,
  });
  await app.request("/api/ping");
  return {
    db,
    github,
    now,
    core: (at: Date = now): Core => ({ d1: db, env, now: () => at, version: "v1" }),
    async heartbeat(part: string, ok: boolean, error: string | null) {
      const at = istText(now);
      await db
        .prepare(
          `insert into heartbeats (part, version, at, ok, error, next_expected_by, last_success) values (?, 'v1', ?, ?, ?, null, null)
           on conflict(part) do update set ok = excluded.ok, error = excluded.error, at = excluded.at`,
        )
        .bind(part, at, ok ? 1 : 0, error)
        .run();
    },
    async browserError(i: number) {
      await db
        .prepare("insert into browser_errors (id, at, message) values (?, ?, 'x')")
        .bind(`e${i}`, istText(now))
        .run();
    },
    async flag(key: string) {
      const r = (await db.prepare("select enabled from flags where key = ?").bind(key).first()) as {
        enabled: number;
      } | null;
      return r?.enabled === 1;
    },
  };
}
