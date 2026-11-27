// Browser errors the page posted to /api/errors; Admin shows them under Problems.
import { index, sqliteTable, text } from "drizzle-orm/sqlite-core";

export const browserErrors = sqliteTable(
  "browser_errors",
  {
    id: text("id").primaryKey(),
    at: text("at").notNull(),
    message: text("message").notNull(),
    stack: text("stack"),
    pane: text("pane"),
    url: text("url"),
    version: text("version"),
    userAgent: text("user_agent"),
  },
  (t) => [index("browser_errors_at").on(t.at)],
);
