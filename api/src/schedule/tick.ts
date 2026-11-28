// The 5-minute tick (decisions §2 Schedules): starts each due Action by `workflow_dispatch`, once. The
// unique job key decides "once": the row is inserted first and only the insert that won dispatches.
import { type Dataset, DISPATCH_GRACE_MINUTES, JOB_MAX_ATTEMPTS } from "@stockpilot/contract";
import type { GithubBot } from "../../../adapters/src/github";
import { istDay, istText } from "../app";
import { loadCalendar } from "../calendar/routes";
import { type Core, isPaused, type JobRow } from "../jobs/runtime";
import { dueRuns } from "./plan";

export const ENGINE_REPO = "stockpilot-hq/stockpilot-engine";
export const PRIVATE_REPO = "stockpilot-hq/stockpilot";
/** Button Jobs whose workflow is not `<kind>.yml` in the engine repo. `documents` (Refresh) runs privately. */
export const BUTTON_JOBS: Record<string, { repo: string; workflow: string }> = {
  documents: { repo: PRIVATE_REPO, workflow: "documents.yml" },
};
const MIN = 60_000;
/** A Job is dispatched this many times at most before it waits for a person. */
export const MAX_DISPATCHES = 5;

export type TickDeps = {
  github: GithubBot;
  datasets: Record<string, Dataset>;
  /** The workflow file that runs a kind (default `<kind>.yml`). */
  workflowFor?: (kind: string) => string;
  ref?: string;
};
export type TickResult = {
  dispatched: string[];
  redispatched: string[];
  retried: string[];
  failed: string[];
};

export async function dispatchJob(
  deps: Pick<TickDeps, "github" | "workflowFor" | "ref">,
  job: Pick<JobRow, "kind" | "subject" | "day" | "range_from" | "range_to">,
): Promise<void> {
  const button = BUTTON_JOBS[job.kind];
  await deps.github.dispatchWorkflow({
    repo: button?.repo ?? ENGINE_REPO,
    workflow: button?.workflow ?? (deps.workflowFor ?? ((k) => `${k}.yml`))(job.kind),
    ref: deps.ref ?? "main",
    inputs: {
      kind: job.kind,
      subject: job.subject,
      day: job.day,
      from: job.range_from,
      to: job.range_to,
    },
  });
}

/** Queue a Job's key if it has none. True when this call created it (and so must dispatch it). */
export async function queueJob(
  core: Core,
  job: { kind: string; subject: string; day: string; from?: string; to?: string },
): Promise<boolean> {
  const now = istText(core.now());
  const r = await core.d1
    .prepare(
      `insert or ignore into job_runs (key, kind, subject, day, status, range_from, range_to, queued_at)
       values (?, ?, ?, ?, 'queued', ?, ?, ?)`,
    )
    .bind(
      `${job.kind}|${job.subject}|${job.day}`,
      job.kind,
      job.subject,
      job.day,
      job.from ?? job.day,
      job.to ?? job.from ?? job.day,
      now,
    )
    .run();
  return r.meta.changes > 0;
}

const mark = (core: Core, key: string, sql: string, ...bind: unknown[]) =>
  core.d1
    .prepare(sql)
    .bind(...bind, key)
    .run();

export async function tick(core: Core, deps: TickDeps): Promise<TickResult> {
  const out: TickResult = { dispatched: [], redispatched: [], retried: [], failed: [] };
  const now = core.now();
  const nowText = istText(now);
  const day = istDay(now);

  const send = async (
    job: JobRow | Pick<JobRow, "kind" | "subject" | "day" | "range_from" | "range_to">,
    key: string,
  ) => {
    try {
      await dispatchJob(deps, job);
      await mark(
        core,
        key,
        "update job_runs set dispatched_at = ?, dispatch_count = dispatch_count + 1 where key = ?",
        nowText,
      );
      return true;
    } catch {
      out.failed.push(key);
      return false;
    }
  };

  // 1. New: every Job whose time has come and that has no key yet.
  const keys = new Set(
    (
      (await core.d1.prepare("select key from job_runs where day = ?").bind(day).all()) as {
        results: { key: string }[];
      }
    ).results.map((r) => r.key),
  );
  const calendar = await loadCalendar(core);
  for (const due of dueRuns({ datasets: deps.datasets, calendar, now, keys })) {
    if (await isPaused(core, due.kind)) continue;
    if (!(await queueJob(core, due))) continue;
    if (
      await send(
        {
          kind: due.kind,
          subject: due.subject,
          day: due.day,
          range_from: due.day,
          range_to: due.day,
        },
        due.key,
      )
    )
      out.dispatched.push(due.key);
  }

  // 2. Dispatched but never started: again, once the grace period has passed.
  const grace = istText(new Date(now.getTime() - DISPATCH_GRACE_MINUTES * MIN));
  const stuck = (
    (await core.d1
      .prepare(
        "select * from job_runs where status = 'queued' and dispatch_count < ? and (dispatched_at is null or dispatched_at <= ?) order by key",
      )
      .bind(MAX_DISPATCHES, grace)
      .all()) as { results: JobRow[] }
  ).results;
  for (const row of stuck) {
    if (await isPaused(core, row.kind)) continue;
    if (await send(row, row.key)) out.redispatched.push(row.key);
  }

  // 3. Failed with tries left and the backoff over: dispatch the next try.
  const retry = (
    (await core.d1
      .prepare(
        "select * from job_runs where status = 'failed' and attempts < ? and retry_at is not null and retry_at <= ? order by key",
      )
      .bind(JOB_MAX_ATTEMPTS, nowText)
      .all()) as { results: JobRow[] }
  ).results;
  for (const row of retry) {
    if (await isPaused(core, row.kind)) continue;
    // Back to queued first: only the tick that won this update dispatches, and a Job that begins
    // takes the queued row as its own.
    const won = await core.d1
      .prepare(
        "update job_runs set status = 'queued', queued_at = ?, dispatched_at = null, dispatch_count = 0 where key = ? and status = 'failed'",
      )
      .bind(nowText, row.key)
      .run();
    if (won.meta.changes === 0) continue;
    if (await send(row, row.key)) out.retried.push(row.key);
  }
  return out;
}
