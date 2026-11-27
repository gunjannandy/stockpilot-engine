// Job runtime tables (decisions §2 Schedules, §6 Jobs).
import { index, integer, primaryKey, sqliteTable, text } from "drizzle-orm/sqlite-core";

/** One row per Job key (kind, subject, day): the unique key that stops a Job doubling up. */
export const jobRuns = sqliteTable(
  "job_runs",
  {
    key: text("key").primaryKey(),
    kind: text("kind").notNull(),
    subject: text("subject").notNull(),
    day: text("day").notNull(),
    runId: text("run_id"),
    status: text("status").notNull(),
    rangeFrom: text("range_from").notNull(),
    rangeTo: text("range_to").notNull(),
    attempts: integer("attempts").notNull().default(0),
    queuedAt: text("queued_at"),
    dispatchedAt: text("dispatched_at"),
    dispatchCount: integer("dispatch_count").notNull().default(0),
    startedAt: text("started_at"),
    finishedAt: text("finished_at"),
    durationMs: integer("duration_ms"),
    result: text("result"),
    error: text("error"),
    retryAt: text("retry_at"),
  },
  (t) => [index("job_runs_kind_finished").on(t.kind, t.finishedAt)],
);

export const jobLocks = sqliteTable("job_locks", {
  kind: text("kind").primaryKey(),
  runId: text("run_id").notNull(),
  expiresAt: text("expires_at").notNull(),
});

export const jobPauses = sqliteTable("job_pauses", {
  kind: text("kind").primaryKey(),
  pausedAt: text("paused_at").notNull(),
});

export const modelUsage = sqliteTable(
  "model_usage",
  {
    day: text("day").notNull(),
    kind: text("kind").notNull(),
    used: integer("used").notNull(),
  },
  (t) => [primaryKey({ columns: [t.day, t.kind] })],
);

export const modelCache = sqliteTable("model_cache", {
  key: text("key").primaryKey(),
  kind: text("kind").notNull(),
  day: text("day").notNull(),
  answer: text("answer").notNull(),
  at: text("at").notNull(),
});
