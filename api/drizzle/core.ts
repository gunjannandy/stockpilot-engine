// Core tables. Each later area keeps its own schema file at api/src/<area>/schema.ts.
import { index, integer, primaryKey, sqliteTable, text } from "drizzle-orm/sqlite-core";

export const ping = sqliteTable("ping", {
  id: text("id").primaryKey(),
  at: text("at").notNull(),
  source: text("source").notNull(),
});

export const jobs = sqliteTable(
  "jobs",
  {
    id: text("id").primaryKey(),
    kind: text("kind").notNull(),
    status: text("status").notNull(),
    result: text("result"),
    error: text("error"),
    startedAt: text("started_at").notNull(),
    finishedAt: text("finished_at"),
  },
  (t) => [index("jobs_kind_started").on(t.kind, t.startedAt)],
);

export const writeBudget = sqliteTable(
  "write_budget",
  {
    day: text("day").notNull(),
    dataset: text("dataset").notNull(),
    writes: integer("writes").notNull(),
  },
  (t) => [primaryKey({ columns: [t.day, t.dataset] })],
);

export const heartbeats = sqliteTable("heartbeats", {
  part: text("part").primaryKey(),
  version: text("version").notNull(),
  at: text("at").notNull(),
  ok: integer("ok", { mode: "boolean" }).notNull(),
  error: text("error"),
  nextExpectedBy: text("next_expected_by"),
  lastSuccess: text("last_success"),
});

export const flags = sqliteTable("flags", {
  key: text("key").primaryKey(),
  enabled: integer("enabled", { mode: "boolean" }).notNull(),
  updatedAt: text("updated_at").notNull(),
});

export const checkResults = sqliteTable("check_results", {
  checkId: text("check_id").primaryKey(),
  ok: integer("ok", { mode: "boolean" }).notNull(),
  at: text("at").notNull(),
  detail: text("detail").notNull(),
});

export const deploys = sqliteTable("deploys", {
  version: text("version").primaryKey(),
  firstSeenAt: text("first_seen_at").notNull(),
});
