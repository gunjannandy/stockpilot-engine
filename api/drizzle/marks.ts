// Marks (MARKS area): one shared "seen" row per dataset row and run, so opening it clears it for both of us.
import { primaryKey, sqliteTable, text } from "drizzle-orm/sqlite-core";

export const markSeen = sqliteTable(
  "mark_seen",
  {
    dataset: text("dataset").notNull(),
    rowKey: text("row_key").notNull(),
    runId: text("run_id").notNull(),
    seenAt: text("seen_at").notNull(),
    byPerson: text("by_person"),
  },
  (t) => [primaryKey({ columns: [t.dataset, t.rowKey, t.runId] })],
);
