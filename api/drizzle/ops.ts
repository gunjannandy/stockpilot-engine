// Operations tables (decisions §6): watcher episodes, the daily promises, dependency checks, rollbacks.
import { integer, primaryKey, sqliteTable, text } from "drizzle-orm/sqlite-core";

/** One row per trouble episode: it stays open (and no second issue is opened) until the thing turns green. */
export const watcherAlerts = sqliteTable("watcher_alerts", {
  subject: text("subject").primaryKey(),
  issue: integer("issue"),
  openedAt: text("opened_at").notNull(),
  closedAt: text("closed_at"),
});

export const promiseResults = sqliteTable(
  "promise_results",
  {
    day: text("day").notNull(),
    promise: text("promise").notNull(),
    ok: integer("ok", { mode: "boolean" }).notNull(),
    detail: text("detail").notNull(),
    at: text("at").notNull(),
  },
  (t) => [primaryKey({ columns: [t.day, t.promise] })],
);

export const depChecks = sqliteTable("dep_checks", {
  dep: text("dep").primaryKey(),
  ok: integer("ok", { mode: "boolean" }).notNull(),
  detail: text("detail").notNull(),
  fallback: text("fallback").notNull(),
  at: text("at").notNull(),
});

/** One row per rolled-back version: the unique key that stops a second rollback and a second hotfix issue. */
export const rollbacks = sqliteTable("rollbacks", {
  version: text("version").primaryKey(),
  at: text("at").notNull(),
  detail: text("detail").notNull(),
  issue: integer("issue"),
});
