// Holdings, trades, corporate actions and Kite syncs: what SYNC and the document readers write and
// PORTFOLIO reads. Every row says whose it is (`account`) and where it came from (`source`), so a second
// account later is data, not a migration. The lots maths in `money/` reads these as plain rows.
import { index, integer, primaryKey, real, sqliteTable, text } from "drizzle-orm/sqlite-core";

/** Kite's holdings, one row per holding per sync (`snapshot_at` is the sync's time, ISO). */
export const holdings = sqliteTable(
  "holdings",
  {
    account: text("account").notNull(),
    source: text("source").notNull(), // kite | coin | cdsl | fidelity
    snapshotAt: text("snapshot_at").notNull(),
    kind: text("kind").notNull(), // stock | mf | rsu
    symbol: text("symbol").notNull(),
    isin: text("isin"),
    quantity: real("quantity").notNull(),
    avgPrice: real("avg_price").notNull(),
  },
  (t) => [
    primaryKey({ columns: [t.account, t.source, t.snapshotAt, t.kind, t.symbol, t.isin] }),
    index("holdings_snapshot").on(t.account, t.snapshotAt),
  ],
);

/** Executed trades and vests from every document and from Kite. `trade_key` is the exchange trade id, else a content key. */
export const trades = sqliteTable(
  "trades",
  {
    tradeKey: text("trade_key").primaryKey(),
    account: text("account").notNull(),
    source: text("source").notNull(), // tradebook | contract_note | coin | cas | fidelity | rsu_inference
    sourceRef: text("source_ref").notNull(),
    kind: text("kind").notNull(), // stock | mf | rsu
    symbol: text("symbol").notNull(),
    isin: text("isin"),
    side: text("side").notNull(), // buy | sell | vest | credit | debit
    tradeDate: text("trade_date").notNull(), // YYYY-MM-DD
    quantity: real("quantity").notNull(),
    price: real("price"),
    currency: text("currency").notNull().default("INR"),
    status: text("status").notNull().default("confirmed"), // "expected" vests never become lots
  },
  (t) => [index("trades_account_date").on(t.account, t.tradeDate), index("trades_isin").on(t.isin)],
);

/** A split, bonus, demerger or rights issue. */
export const corporateActions = sqliteTable(
  "corporate_actions",
  {
    symbol: text("symbol").notNull(),
    exDate: text("ex_date").notNull(),
    kind: text("kind").notNull(), // split | bonus | demerger | rights
    isin: text("isin"),
    numerator: real("numerator").notNull(),
    denominator: real("denominator").notNull(),
    subject: text("subject").notNull().default(""),
    source: text("source").notNull().default("nse"), // nse | yfinance | owner
  },
  (t) => [primaryKey({ columns: [t.symbol, t.exDate, t.kind] })],
);

/** The numbers NSE does not give: a demerger's new company and the share of cost that moves, a rights issue's price. */
export const actionTerms = sqliteTable(
  "action_terms",
  {
    symbol: text("symbol").notNull(),
    exDate: text("ex_date").notNull(),
    kind: text("kind").notNull(),
    newIsin: text("new_isin"),
    newSymbol: text("new_symbol"),
    costFraction: real("cost_fraction"),
    price: real("price"),
  },
  (t) => [primaryKey({ columns: [t.symbol, t.exDate, t.kind] })],
);

/** What each Kite sync read, kept whole (JSON text) so the Sync steps can say "done, 3 changes". */
export const kiteSyncs = sqliteTable(
  "kite_syncs",
  {
    account: text("account").notNull(),
    source: text("source").notNull().default("kite"),
    fetchedAt: text("fetched_at").notNull(),
    trades: text("trades"),
    positions: text("positions"),
    margins: text("margins"),
    gtts: text("gtts"),
    changes: integer("changes"),
  },
  (t) => [primaryKey({ columns: [t.account, t.fetchedAt] })],
);
