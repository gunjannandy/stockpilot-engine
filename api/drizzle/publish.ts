// Publishing tables (decisions §2): runs, their staged rows, held-back rows and each dataset's current-run pointer.
import { integer, primaryKey, sqliteTable, text } from "drizzle-orm/sqlite-core";

export const runs = sqliteTable(
  "runs",
  {
    dataset: text("dataset").notNull(),
    runId: text("run_id").notNull(),
    status: text("status").notNull(),
    source: text("source").notNull(),
    fetchedAt: text("fetched_at").notNull(),
    asOf: text("as_of").notNull(),
    accepted: integer("accepted").notNull().default(0),
    held: integer("held").notNull().default(0),
    refused: integer("refused").notNull().default(0),
    startedAt: text("started_at").notNull(),
    finishedAt: text("finished_at"),
    error: text("error"),
  },
  (t) => [primaryKey({ columns: [t.dataset, t.runId] })],
);

export const datasetRows = sqliteTable(
  "dataset_rows",
  {
    dataset: text("dataset").notNull(),
    runId: text("run_id").notNull(),
    seq: integer("seq").notNull(),
    body: text("body").notNull(),
  },
  (t) => [primaryKey({ columns: [t.dataset, t.runId, t.seq] })],
);

export const heldRows = sqliteTable(
  "held_rows",
  {
    dataset: text("dataset").notNull(),
    runId: text("run_id").notNull(),
    seq: integer("seq").notNull(),
    reason: text("reason").notNull(),
    body: text("body").notNull(),
  },
  (t) => [primaryKey({ columns: [t.dataset, t.runId, t.seq] })],
);

export const pointers = sqliteTable("pointers", {
  dataset: text("dataset").primaryKey(),
  runId: text("run_id").notNull(),
  previousRunId: text("previous_run_id"),
  asOf: text("as_of").notNull(),
  publishedAt: text("published_at").notNull(),
  rows: integer("rows").notNull(),
  file: text("file"),
  summary: text("summary").notNull(),
});
