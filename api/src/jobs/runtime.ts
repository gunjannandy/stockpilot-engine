// The Job runtime (decisions §6): a unique key per (kind, subject, day), one lock per kind, retry with
// backoff, an expected time from past runs, a pause per kind. Python only calls begin and end.
import { JOB_MAX_ATTEMPTS } from "@stockpilot/contract";
import type { Ctx } from "../app";
import { istDay, istText } from "../app";

/** What the runtime needs of a request or a cron duty: the database, the clock, the env and the version. */
export type Core = Pick<Ctx, "d1" | "now" | "env" | "version">;

export const LOCK_TTL_MINUTES = 120;
const MIN = 60_000;

export const jobKey = (kind: string, subject: string, day: string) => `${kind}|${subject}|${day}`;

/** Minutes a failed Job waits before its next try: 2, 4, 8 … capped at an hour. */
export const backoffMinutes = (failures: number) => Math.min(60, 2 ** Math.max(1, failures));

/** Run `fn`, and on a throw wait (doubling from `baseMs`) and try again, up to `attempts` runs in all. */
export async function withRetry<T>(
  fn: () => Promise<T>,
  opts: { attempts: number; baseMs: number; sleep?: (ms: number) => Promise<void> },
): Promise<T> {
  const sleep = opts.sleep ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));
  for (let i = 1; ; i++) {
    try {
      return await fn();
    } catch (err) {
      if (i >= opts.attempts) throw err;
      await sleep(opts.baseMs * 2 ** (i - 1));
    }
  }
}

export type JobRow = {
  key: string;
  kind: string;
  subject: string;
  day: string;
  run_id: string | null;
  status: "queued" | "running" | "done" | "failed";
  range_from: string;
  range_to: string;
  attempts: number;
  queued_at: string | null;
  dispatched_at: string | null;
  dispatch_count: number;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  result: string | null;
  error: string | null;
  retry_at: string | null;
};

export const getJob = async (ctx: Core, key: string) =>
  (await ctx.d1.prepare("select * from job_runs where key = ?").bind(key).first()) as JobRow | null;

export const isPaused = async (ctx: Core, kind: string) =>
  (await ctx.d1.prepare("select 1 as p from job_pauses where kind = ?").bind(kind).first()) !==
  null;

/** Median seconds of the kind's last five finished runs, or null with none. */
export async function expectedSeconds(ctx: Core, kind: string): Promise<number | null> {
  const r = (await ctx.d1
    .prepare(
      "select duration_ms from job_runs where kind = ? and status = 'done' and duration_ms is not null order by finished_at desc limit 5",
    )
    .bind(kind)
    .all()) as { results: { duration_ms: number }[] };
  const d = r.results.map((x) => x.duration_ms).sort((a, b) => a - b);
  if (d.length === 0) return null;
  const mid = d.length >> 1;
  const median =
    d.length % 2 ? (d[mid] as number) : ((d[mid - 1] as number) + (d[mid] as number)) / 2;
  return Math.round(median / 1000);
}

export type Begin = {
  kind: string;
  subject: string;
  day: string;
  runId: string;
  from: string;
  to: string;
  rerun: boolean;
};
export type BeginResult =
  | { ok: true; key: string; startedAt: string; range: { from: string; to: string } }
  | { ok: false; status: 409 | 423; error: string };

/** Take the key and the kind's lock for a Job that is starting. */
export async function beginJob(ctx: Core, b: Begin): Promise<BeginResult> {
  const now = ctx.now();
  const nowText = istText(now);
  const key = jobKey(b.kind, b.subject, b.day);
  if (await isPaused(ctx, b.kind)) return { ok: false, status: 423, error: `${b.kind} is paused` };

  const existing = await getJob(ctx, key);
  if (existing) {
    const lock = (await ctx.d1
      .prepare("select run_id, expires_at from job_locks where kind = ?")
      .bind(b.kind)
      .first()) as { run_id: string; expires_at: string } | null;
    const stale =
      existing.status === "running" &&
      (!lock || lock.run_id !== existing.run_id || lock.expires_at < nowText);
    const retryDue =
      existing.status === "failed" &&
      existing.attempts < JOB_MAX_ATTEMPTS &&
      existing.retry_at !== null &&
      existing.retry_at <= nowText;
    const allowed = existing.status === "queued" || stale || retryDue || b.rerun;
    if (!allowed) {
      const why =
        existing.status === "failed"
          ? existing.retry_at
            ? `failed, next try not before ${existing.retry_at}`
            : "failed and out of tries"
          : existing.status;
      return { ok: false, status: 409, error: `duplicate: ${key} is ${why}` };
    }
  }

  // The kind's lock: one running Job per kind. `insert or ignore` is the atomic grab.
  const expires = istText(new Date(now.getTime() + LOCK_TTL_MINUTES * MIN));
  const grab = await ctx.d1
    .prepare("insert or ignore into job_locks (kind, run_id, expires_at) values (?, ?, ?)")
    .bind(b.kind, b.runId, expires)
    .run();
  if (grab.meta.changes === 0) {
    const took = await ctx.d1
      .prepare(
        "update job_locks set run_id = ?, expires_at = ? where kind = ? and (expires_at < ? or run_id = ?)",
      )
      .bind(b.runId, expires, b.kind, nowText, b.runId)
      .run();
    if (took.meta.changes === 0)
      return { ok: false, status: 423, error: `locked: another ${b.kind} Job is running` };
  }

  const reset = existing && (existing.status === "done" || b.rerun) ? 0 : (existing?.attempts ?? 0);
  await ctx.d1
    .prepare(
      `insert into job_runs (key, kind, subject, day, run_id, status, range_from, range_to, attempts, started_at)
       values (?, ?, ?, ?, ?, 'running', ?, ?, ?, ?)
       on conflict(key) do update set run_id = excluded.run_id, status = 'running', range_from = excluded.range_from,
         range_to = excluded.range_to, attempts = excluded.attempts, started_at = excluded.started_at,
         finished_at = null, duration_ms = null, result = null, error = null, retry_at = null`,
    )
    .bind(key, b.kind, b.subject, b.day, b.runId, b.from, b.to, reset, nowText)
    .run();
  return { ok: true, key, startedAt: nowText, range: { from: b.from, to: b.to } };
}

export type End = {
  runId: string;
  status: "done" | "failed";
  result?: string | null;
  error?: string | null;
};

/** Finish a running Job: free the lock; a failure schedules the next try with backoff, up to the limit. */
export async function endJob(ctx: Core, e: End): Promise<{ ok: boolean; retryAt?: string | null }> {
  const now = ctx.now();
  const row = (await ctx.d1
    .prepare("select * from job_runs where run_id = ? and status = 'running'")
    .bind(e.runId)
    .first()) as JobRow | null;
  if (!row) return { ok: false };
  const started = row.started_at ? Date.parse(row.started_at) : now.getTime();
  const duration = Math.max(0, now.getTime() - started);
  const failures = row.attempts + (e.status === "failed" ? 1 : 0);
  const retryAt =
    e.status === "failed" && failures < JOB_MAX_ATTEMPTS
      ? istText(new Date(now.getTime() + backoffMinutes(failures) * MIN))
      : null;
  await ctx.d1
    .prepare(
      "update job_runs set status = ?, finished_at = ?, duration_ms = ?, result = ?, error = ?, attempts = ?, retry_at = ? where key = ? and run_id = ?",
    )
    .bind(
      e.status,
      istText(now),
      duration,
      e.result ?? null,
      e.error ?? null,
      failures,
      retryAt,
      row.key,
      e.runId,
    )
    .run();
  await ctx.d1
    .prepare("delete from job_locks where kind = ? and run_id = ?")
    .bind(row.kind, e.runId)
    .run();
  return { ok: true, retryAt };
}

export { istDay };
