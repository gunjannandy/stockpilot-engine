// The per-table list: for every v2 table (the 13 in D1, the KV queue, the vault's tables), copy, rebuild
// or drop, with the reason. `copy` rows are moved by the owning area's map; `rebuild` rows are made again
// from documents by the readers; `drop` rows are not carried. A table not on this list fails the report.
import type { Entry, Kind } from "./types";

const e = (
  kind: Kind,
  table: string,
  action: Entry["action"],
  area: string,
  reason: string,
): Entry => ({
  kind,
  table,
  action,
  area,
  reason,
});
const d1 = (t: string, a: Entry["action"], area: string, why: string) => e("d1", t, a, area, why);
const vault = (t: string, a: Entry["action"], area: string, why: string) =>
  e("vault", t, a, area, why);

const REFETCHED = "public data, fetched again by its own Job";
const DERIVED = "derived from other rows, rebuilt by v3";
const DOCUMENT = "document rows, rebuilt by the readers from the owner's documents";

export const LIST: Entry[] = [
  d1("asks", "copy", "feedback", "the owner's and father's asks"),
  d1("feedback", "copy", "feedback", "what was said during the upgrade is never lost"),
  d1("calls", "copy", "calls", "the last calls and their dates"),
  d1("lists", "copy", "lists", "the watchlist and picks as they stand"),
  d1("changes", "drop", "calls", "change marks are a derived view; v3 makes its own"),
  d1("job_lines", "drop", "core", "v2 job step trails; v3 Jobs keep their own"),
  d1("jobs", "drop", "core", "v2 job queue; v3 Jobs keep their own"),
  d1("news_items", "drop", "news", REFETCHED),
  d1("news_tags", "drop", "news", "v2 fanned news out by sector; v3 impact rows replace them"),
  d1("news_rank", "drop", "news", "v2 rank with the sector spread v3 removes"),
  d1("quotes", "drop", "core", "live prices, filled again within minutes"),
  d1("views", "drop", "core", "v2's private screen documents, derived"),
  d1("write_budget", "drop", "core", "a day counter"),
  e("kv", "queue", "drop", "core", "the VM's request queue is retired; v3 has no VM"),

  vault("holdings", "copy", "portfolio", "every Kite snapshot, the base of the portfolio"),
  vault("trades", "copy", "portfolio", "every executed trade and vest"),
  vault("trade_tags", "copy", "portfolio", "who placed each trade and how"),
  vault("kite_syncs", "copy", "portfolio", "what each Kite sync read"),
  vault("corporate_actions", "copy", "portfolio", "splits, bonuses and demergers already found"),
  vault("action_terms", "copy", "portfolio", "numbers the owner entered by hand"),
  vault(
    "lots",
    "rebuild",
    "portfolio",
    "lots are made again from trades and corporate actions by the money package",
  ),
  vault("sales", "rebuild", "portfolio", DOCUMENT),
  vault("fidelity_lots", "rebuild", "portfolio", DOCUMENT),
  vault("fidelity_events", "rebuild", "portfolio", DOCUMENT),
  vault("fidelity_holdings", "rebuild", "portfolio", DOCUMENT),
  vault("documents", "rebuild", "portfolio", DOCUMENT),
  vault("holding_statements", "rebuild", "portfolio", DOCUMENT),
  vault("itr_documents", "rebuild", "tax", DOCUMENT),
  vault("payslip_perquisites", "rebuild", "tax", DOCUMENT),
  vault("console_pnl", "rebuild", "tax", DOCUMENT),
  vault("console_pnl_totals", "rebuild", "tax", DOCUMENT),
  vault("watchlist", "copy", "lists", "the owner's watchlist"),
  vault("not_now", "copy", "lists", "stocks set aside by the owner"),
  vault("calls", "copy", "calls", "every call ever made, the track record's base"),
  vault("archived_days", "copy", "record", "each day's archived page"),
  vault("long_term_marks", "copy", "record", "the 'I hold this for years' marks"),
  vault("fund_calls", "copy", "calls", "fund calls made so far"),
  vault(
    "smallcase_orders",
    "copy",
    "record",
    "Smallcase orders, for the record against our trades",
  ),
  vault("feedback", "copy", "feedback", "the same asks, private copy"),
  vault("target_allocations", "copy", "settings", "the owner's target mix"),
  vault("budgets", "copy", "settings", "the owner's budget"),
  ...[
    "runs",
    "screens",
    "base_rate_buckets",
    "base_rates",
    "fund_base_rates",
    "fetch_log",
    "gaps",
    "headlines",
    "announcements",
    "filings_index",
    "flows",
    "deals",
    "delivery",
    "fundamentals",
    "quarterly",
    "ownership",
    "holidays",
    "index_levels",
    "prices",
    "navs",
    "funds",
    "fund_costs",
    "fx",
    "surveillance",
    "stocks",
    "results_calendar",
    "price_flags",
    "demerger_factors",
  ].map((t) => vault(t, "drop", "core", REFETCHED)),
  ...[
    "site_extras",
    "weekly_reports",
    "feedback_changes",
    "learned_forgotten",
    "house_rule_edits",
    "analyst_asks",
    "problems",
  ].map((t) => vault(t, "drop", "core", `${DERIVED}, or a dropped v2 feature`)),
  vault("requests", "drop", "core", "the VM's request queue is retired"),
  vault("schema_migrations", "drop", "core", "v2's own bookkeeping"),
];

export const keyOf = (kind: Kind, table: string) => `${kind}:${table}`;
