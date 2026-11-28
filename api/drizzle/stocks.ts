import { integer, primaryKey, real, sqliteTable, text } from "drizzle-orm/sqlite-core";

export const stockHistory = sqliteTable(
  "stock_history",
  {
    symbol: text("symbol").notNull(),
    exchange: text("exchange").notNull(),
    date: text("date").notNull(),
    open: real("open"),
    high: real("high"),
    low: real("low"),
    close: real("close").notNull(),
    prevClose: real("prev_close"),
    volume: real("volume"),
  },
  (t) => [primaryKey({ columns: [t.symbol, t.exchange, t.date] })],
);

export const quoteCache = sqliteTable("quote_cache", {
  symbol: text("symbol").primaryKey(),
  price: real("price").notNull(),
  prevClose: real("prev_close"),
  at: text("at").notNull(),
  atMs: integer("at_ms").notNull(),
});
