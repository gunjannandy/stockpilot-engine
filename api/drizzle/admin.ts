// Usage counts: one row per day, screen and button (a screen-only hit has button "").
import { integer, primaryKey, sqliteTable, text } from "drizzle-orm/sqlite-core";

export const usageCounts = sqliteTable(
  "usage_counts",
  {
    day: text("day").notNull(),
    screen: text("screen").notNull(),
    button: text("button").notNull(),
    n: integer("n").notNull(),
  },
  (t) => [primaryKey({ columns: [t.day, t.screen, t.button] })],
);
