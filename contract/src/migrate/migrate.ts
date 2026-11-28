import { z } from "zod";

/** Tables only the one-time v2 copy writes. The ingest door takes these beside the registry's datasets, signed the
 * same way, with no day budget (the copy is one way, once, and reruns replace by key). A row is checked against
 * `row` and held back when it does not fit; `keys` are the table's key columns, so a rerun replaces a row (nulls
 * compared as equal) and never doubles it. `row`'s fields are exactly the table's columns. */
export type MigrationDataset = {
  table: string;
  keys: string[];
  row: z.ZodObject;
};

const nstr = z.string().nullable();
const nnum = z.number().nullable();
const day = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);

export const migrationDatasets = {
  holdings: {
    table: "holdings",
    keys: ["account", "source", "snapshot_at", "kind", "symbol", "isin"],
    row: z.object({
      account: z.string(),
      source: z.string(),
      snapshot_at: z.string(),
      kind: z.string(),
      symbol: z.string().min(1),
      isin: nstr,
      quantity: z.number(),
      avg_price: z.number(),
    }),
  },
  trades: {
    table: "trades",
    keys: ["trade_key"],
    row: z.object({
      trade_key: z.string().min(1),
      account: z.string(),
      source: z.string(),
      source_ref: z.string(),
      kind: z.string(),
      symbol: z.string().min(1),
      isin: nstr,
      side: z.string(),
      trade_date: day,
      quantity: z.number(),
      price: nnum,
      currency: z.string(),
      status: z.string(),
    }),
  },
  trade_tags: {
    table: "trade_tags",
    keys: ["trade_key"],
    row: z.object({
      trade_key: z.string().min(1),
      placed_by: nstr,
      basket: nstr,
      how: nstr,
    }),
  },
  kite_syncs: {
    table: "kite_syncs",
    keys: ["account", "fetched_at"],
    row: z.object({
      account: z.string(),
      source: z.string(),
      fetched_at: z.string(),
      trades: nstr,
      positions: nstr,
      margins: nstr,
      gtts: nstr,
      changes: z.number().int().nullable(),
    }),
  },
  corporate_actions: {
    table: "corporate_actions",
    keys: ["symbol", "ex_date", "kind"],
    row: z.object({
      symbol: z.string().min(1),
      ex_date: day,
      kind: z.string(),
      isin: nstr,
      numerator: z.number(),
      denominator: z.number(),
      subject: z.string(),
      source: z.string(),
    }),
  },
  action_terms: {
    table: "action_terms",
    keys: ["symbol", "ex_date", "kind"],
    row: z.object({
      symbol: z.string().min(1),
      ex_date: day,
      kind: z.string(),
      new_isin: nstr,
      new_symbol: nstr,
      cost_fraction: nnum,
      price: nnum,
    }),
  },
  money_budgets: {
    table: "money_budgets",
    keys: ["month"],
    row: z.object({ month: z.string(), amount_inr: z.number(), updated_at: z.string() }),
  },
  money_mix: {
    table: "money_mix",
    keys: ["asset_class"],
    row: z.object({ asset_class: z.string(), share: z.number(), updated_at: z.string() }),
  },
  calls: {
    table: "calls",
    keys: ["id"],
    row: z.object({
      id: z.string().min(1),
      symbol: z.string().min(1),
      exchange: z.enum(["NSE", "BSE"]),
      made_on: day,
      verdict: z.string(),
      chance: nnum,
      horizon_days: z.number().int(),
      base_cases: z.number().int(),
      base_rate: nnum,
      sell_line: z.number(),
      buy_line: z.number(),
      could_rise_to: nnum,
      would_buy_at: nnum,
      sell_at_once_at: nnum,
      limited: z.number().int().min(0).max(1),
      sentences_json: z.string(),
      similar_n: z.number().int(),
      similar_beat: z.number().int(),
      model_version: z.string(),
    }),
  },
  list_rows: {
    table: "list_rows",
    keys: ["id"],
    row: z.object({
      id: z.string().min(1),
      list: z.string(),
      symbol: z.string().min(1),
      exchange: z.enum(["NSE", "BSE"]),
      position: z.number().int().min(1),
      reasons_json: z.string(),
      updated_at: z.string(),
    }),
  },
  watchlist: {
    table: "watchlist",
    keys: ["id"],
    row: z.object({
      id: z.string().min(1),
      kind: z.enum(["stock", "fund"]),
      name: nstr,
      added_at: z.string(),
    }),
  },
  not_now: {
    table: "not_now",
    keys: ["symbol"],
    row: z.object({ symbol: z.string().min(1), until: z.string(), created_at: z.string() }),
  },
  // v2's record rows keep their whole v2 row as JSON text: nothing is lost, and the record screens read them
  // through the Job that rebuilds scores. `payload` is that JSON.
  archived_days: {
    table: "archived_days",
    keys: ["day"],
    row: z.object({ day, payload: z.string() }),
  },
  long_term_marks: {
    table: "long_term_marks",
    keys: ["symbol"],
    row: z.object({ symbol: z.string().min(1), marked_at: z.string(), payload: z.string() }),
  },
  smallcase_orders: {
    table: "smallcase_orders",
    keys: ["order_key"],
    row: z.object({ order_key: z.string().min(1), placed_at: z.string(), payload: z.string() }),
  },
} as const satisfies Record<string, MigrationDataset>;
export type MigrationDatasetName = keyof typeof migrationDatasets;
