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

export const benchReports = sqliteTable("bench_reports", {
  at: text("at").primaryKey(),
  fingerprint: text("fingerprint").notNull(),
  model: text("model").notNull(),
  red: text("red").notNull(),
  body: text("body").notNull(),
});

export const benchState = sqliteTable("bench_state", {
  key: text("key").primaryKey(),
  value: text("value").notNull(),
});

export const fundAnalyseCalls = sqliteTable(
  "fund_analyse_calls",
  {
    key: text("key").primaryKey(),
    fund: text("fund").notNull(),
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
  (t) => [index("fund_analyse_calls_fund").on(t.fund, t.day)],
);
