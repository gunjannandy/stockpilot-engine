// Owner-only money settings. The monthly buy budget is one row per month (`default` is the fallback figure);
// the target mix is one row per asset class. Both keep what v2 kept, so the migration is row for row.
import { real, sqliteTable, text } from "drizzle-orm/sqlite-core";

export const moneyBudgets = sqliteTable("money_budgets", {
  month: text("month").primaryKey(), // YYYY-MM, or "default"
  amountInr: real("amount_inr").notNull(),
  updatedAt: text("updated_at").notNull(),
});

export const moneyMix = sqliteTable("money_mix", {
  assetClass: text("asset_class").primaryKey(), // a key of money's LABELS
  share: real("share").notNull(),
  updatedAt: text("updated_at").notNull(),
});
