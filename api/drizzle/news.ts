import { index, integer, sqliteTable, text } from "drizzle-orm/sqlite-core";

export const newsItems = sqliteTable("news_items", {
  id: text("id").primaryKey(),
  link: text("link").notNull(),
  title: text("title").notNull(),
  source: text("source").notNull(),
  publishedAt: text("published_at").notNull(),
  sourceCount: integer("source_count").notNull(),
  weight: integer("weight").notNull(),
});

/** Append-only: the Worker only inserts (checks/C-079-1 scans for any update or delete). */
export const newsImpact = sqliteTable(
  "news_impact",
  {
    id: text("id").primaryKey(),
    itemId: text("item_id").notNull(),
    symbol: text("symbol").notNull(),
    exchange: text("exchange").notNull(),
    relation: text("relation").notNull(),
    direction: text("direction"),
    size: text("size").notNull(),
    sectorOnly: integer("sector_only").notNull(),
    whyEn: text("why_en").notNull(),
    whyBn: text("why_bn").notNull(),
    weight: integer("weight").notNull(),
    judgedAt: text("judged_at").notNull(),
  },
  (t) => [index("news_impact_symbol").on(t.symbol, t.judgedAt)],
);
