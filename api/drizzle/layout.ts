// The layout row (SHELL area): rail order, hidden screens. One row, key "default"; absent means the folder defaults.
import { sqliteTable, text } from "drizzle-orm/sqlite-core";

export const layout = sqliteTable("layout", {
  key: text("key").primaryKey(),
  json: text("json").notNull(),
  updatedAt: text("updated_at").notNull(),
});
