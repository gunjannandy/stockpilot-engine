import { index, real, sqliteTable, text } from "drizzle-orm/sqlite-core";

export const postmortems = sqliteTable(
  "postmortems",
  {
    callKey: text("call_key").primaryKey(),
    symbol: text("symbol").notNull(),
    day: text("day").notNull(),
    call: text("call").notNull(),
    excessPct: real("excess_pct").notNull(),
    cause: text("cause").notNull(),
    whyEn: text("why_en").notNull(),
    whyBn: text("why_bn").notNull(),
    evidence: text("evidence").notNull(),
    source: text("source").notNull(),
    model: text("model"),
    storedAt: text("stored_at").notNull(),
  },
  (t) => [index("postmortems_stored").on(t.storedAt)],
);

export const nightlyNotes = sqliteTable("nightly_notes", {
  day: text("day").primaryKey(),
  textEn: text("text_en").notNull(),
  textBn: text("text_bn").notNull(),
  storedAt: text("stored_at").notNull(),
});
