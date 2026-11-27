// Test helpers for the scheduler: the real app over SQLite with a fake GitHub bot and small test datasets.
import type { CalendarRow, Dataset } from "@stockpilot/contract";
import { z } from "zod";
import { SqliteD1 } from "../../../adapters/src/core";
import { type FakeGithub, fakeGithub } from "../../../adapters/src/github";
import { loadRegistry } from "../../migrate/discover";
import { createApp, type Env, istText, sign } from "../app";
import { jobRoutes } from "../jobs/routes";
import type { Core } from "../jobs/runtime";
import { KEY } from "../testkit";
import { scheduleRoutes } from "./routes";
import { tick } from "./tick";

const base = {
  table: "ping",
  schedule: "in tests",
  freshnessHours: 24,
  checks: { row: [], run: [] },
  recomputable: true,
  writeBudget: 10,
  row: z.object({ id: z.string() }),
};
export const morning: Dataset = {
  ...base,
  name: "morning",
  job: "ping",
  run: { at: "09:00", on: "trading" },
};
export const daily: Dataset = {
  ...base,
  name: "calendar",
  job: "calendar",
  run: { at: "07:00", on: "every" },
};

export async function scheduleApp(
  opts: {
    now?: () => Date;
    /** The datasets the tick schedules (default: the morning Job, plus the calendar with `withDaily`). */
    datasets?: Dataset[];
    withDaily?: boolean;
    failDispatch?: () => boolean;
    env?: Partial<Env>;
  } = {},
) {
  const db = new SqliteD1();
  const github: FakeGithub = fakeGithub({ failDispatch: opts.failDispatch });
  const registry = await loadRegistry();
  registry.areas = registry.areas.map((a) =>
    a.name === "schedule"
      ? { ...a, routes: (ctx) => scheduleRoutes(ctx, { github }) }
      : a.name === "jobs"
        ? { ...a, routes: (ctx) => jobRoutes(ctx) }
        : a,
  );
  const env = {
    INGEST_HMAC_KEY: KEY,
    HEALTH_SECRET: "h".repeat(24),
    SP_ENV: "dev",
    ...opts.env,
  } as never;
  const app = createApp({ d1: db, env, registry, version: "v1", now: opts.now });
  // The first request applies the migrations.
  await app.request("/api/ping");
  const core = (now: Date): Core => ({ d1: db, env, now: () => now, version: "v1" });
  const datasets = Object.fromEntries(
    (opts.datasets ?? [morning, ...(opts.withDaily ? [daily] : [])]).map((d) => [d.name, d]),
  );
  const signed = async (method: string, path: string, body?: unknown) => {
    const raw = body === undefined ? "" : JSON.stringify(body);
    return app.request(path, {
      method,
      body: body === undefined ? undefined : raw,
      headers: { "content-type": "application/json", "x-signature": await sign(KEY, raw) },
    });
  };
  return {
    app,
    db,
    github,
    core,
    tick: (now: Date) => tick(core(now), { github, datasets }),
    press: (body: Record<string, unknown>) =>
      app.request("/api/job/press", {
        method: "POST",
        body: JSON.stringify(body),
        headers: { "content-type": "application/json" },
      }),
    begin: (body: Record<string, unknown>) => signed("POST", "/api/job/begin", body),
    /** Put the calendar dataset's current run in place without going through the door. */
    async setCalendar(rows: Partial<CalendarRow>[]) {
      const blank = {
        reason: null,
        symbol: null,
        old_shares: null,
        new_shares: null,
        new_symbol: null,
      };
      await db
        .prepare(
          "insert or replace into pointers (dataset, run_id, previous_run_id, as_of, published_at, rows, file, summary) values ('calendar', 'c1', null, '2026-11-26', 'x', ?, null, '{}')",
        )
        .bind(rows.length)
        .run();
      await db.prepare("delete from dataset_rows where dataset = 'calendar'").run();
      for (const [i, r] of rows.entries())
        await db
          .prepare(
            "insert into dataset_rows (dataset, run_id, seq, body) values ('calendar', 'c1', ?, ?)",
          )
          .bind(i, JSON.stringify({ ...blank, ...r }))
          .run();
    },
    /** Mark a keyed Job failed with a retry time and an attempt count. */
    async fail(key: string, retryAt: string | null, error: string, attempts: number) {
      await db
        .prepare(
          "update job_runs set status = 'failed', error = ?, retry_at = ?, attempts = ?, finished_at = ? where key = ?",
        )
        .bind(error, retryAt, attempts, istText(new Date()), key)
        .run();
    },
  };
}
