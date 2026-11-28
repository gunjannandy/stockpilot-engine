import { index, real, sqliteTable, text } from "drizzle-orm/sqlite-core";

export const analyseCalls = sqliteTable(
  "analyse_calls",
  {
    key: text("key").primaryKey(),
    symbol: text("symbol").notNull(),
    day: text("day").notNull(),
    call: text("call").notNull(),
    chancePct: real("chance_pct").notNull(),
    source: text("source").notNull(),
    summaryEn: text("summary_en"),
    summaryBn: text("summary_bn"),
    reasons: text("reasons").notNull(),
    risks: text("risks").notNull(),
    model: text("model"),
    note: text("note"),
    storedAt: text("stored_at").notNull(),
  },
  (t) => [index("analyse_calls_symbol").on(t.symbol, t.day)],
);
