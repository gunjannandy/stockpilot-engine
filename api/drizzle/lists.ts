import { sqliteTable, text } from "drizzle-orm/sqlite-core";

export const watchlist = sqliteTable("watchlist", {
  id: text("id").primaryKey(),
  kind: text("kind").notNull(),
  name: text("name"),
  addedAt: text("added_at").notNull(),
});

export const notNow = sqliteTable("not_now", {
  symbol: text("symbol").primaryKey(),
  until: text("until").notNull(),
  createdAt: text("created_at").notNull(),
});
