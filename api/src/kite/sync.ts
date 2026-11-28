// What a Sync does with what Kite answered: keep the raw holdings and trades with `account` and
// `source` on every row, count the changes against the last sync, and write one kite_syncs row.
import {
  type RawHolding,
  RawHolding as RawHoldingSchema,
  type RawTrade,
  RawTrade as RawTradeSchema,
} from "@stockpilot/contract";
import type { KiteData } from "../../../adapters/src/kite";
import { type Ctx, istText } from "../app";

export const ACCOUNT = "primary";
export const SOURCE = "kite";

type Row = Record<string, unknown>;
const num = (v: unknown) => (typeof v === "number" ? v : Number(v ?? 0)) || 0;
const str = (v: unknown) => (typeof v === "string" ? v : "");

export function mapHoldings(data: KiteData, snapshotAt: string): RawHolding[] {
  const make = (kind: "stock" | "mf") => (r: Row) => ({
    account: ACCOUNT,
    source: SOURCE,
    snapshot_at: snapshotAt,
    kind,
    symbol: str(r.tradingsymbol),
    isin: str(r.isin) || (kind === "mf" ? str(r.tradingsymbol) : "") || null,
    quantity: num(r.quantity) + num(r.t1_quantity),
    avg_price: num(r.average_price),
  });
  return [...data.holdings.map(make("stock")), ...data.mf_holdings.map(make("mf"))].filter(
    (h) => h.symbol && h.quantity !== 0,
  );
}

export function mapTrades(data: KiteData): RawTrade[] {
  return data.trades.map((r) => ({
    account: ACCOUNT,
    source: SOURCE,
    trade_key: `kite:${str(r.trade_id)}`,
    source_ref: str(r.order_id),
    kind: "stock" as const,
    symbol: str(r.tradingsymbol),
    isin: null,
    side: str(r.transaction_type).toLowerCase() === "sell" ? ("sell" as const) : ("buy" as const),
    trade_date: str(r.fill_timestamp || r.order_timestamp).slice(0, 10),
    quantity: num(r.quantity),
    price: num(r.average_price),
  }));
}

export type Stored = { fetchedAt: string; holdings: number; trades: number; changes: number };

/** Store a sync. Rows without an account or a source are rejected (C-068-1); nothing is half-written. */
export async function storeSync(ctx: Pick<Ctx, "d1" | "now">, data: KiteData): Promise<Stored> {
  const at = istText(ctx.now());
  const holdings = mapHoldings(data, at).map((h) => RawHoldingSchema.parse(h));
  const trades = mapTrades(data)
    .filter((t) => t.symbol)
    .map((t) => RawTradeSchema.parse(t));

  const prevAt = (
    (await ctx.d1
      .prepare("select max(snapshot_at) as at from holdings where account = ? and source = ?")
      .bind(ACCOUNT, SOURCE)
      .first()) as { at: string | null } | null
  )?.at;
  const before = new Map<string, number>();
  if (prevAt) {
    const r = (await ctx.d1
      .prepare(
        "select kind, symbol, quantity from holdings where account = ? and source = ? and snapshot_at = ?",
      )
      .bind(ACCOUNT, SOURCE, prevAt)
      .all()) as { results: { kind: string; symbol: string; quantity: number }[] };
    for (const x of r.results) before.set(`${x.kind}|${x.symbol}`, x.quantity);
  }
  let changes = 0;
  const seen = new Set<string>();
  for (const h of holdings) {
    const k = `${h.kind}|${h.symbol}`;
    seen.add(k);
    if (before.get(k) !== h.quantity) changes++;
  }
  for (const k of before.keys()) if (!seen.has(k)) changes++;

  const stmts = [
    ...holdings.map((h) =>
      ctx.d1
        .prepare(
          "insert or replace into holdings (account, source, snapshot_at, kind, symbol, isin, quantity, avg_price) values (?, ?, ?, ?, ?, ?, ?, ?)",
        )
        .bind(
          h.account,
          h.source,
          h.snapshot_at,
          h.kind,
          h.symbol,
          h.isin,
          h.quantity,
          h.avg_price,
        ),
    ),
    ...trades.map((t) =>
      ctx.d1
        .prepare(
          "insert or ignore into trades (trade_key, account, source, source_ref, kind, symbol, isin, side, trade_date, quantity, price) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        )
        .bind(
          t.trade_key,
          t.account,
          t.source,
          t.source_ref,
          t.kind,
          t.symbol,
          t.isin,
          t.side,
          t.trade_date,
          t.quantity,
          t.price,
        ),
    ),
  ];
  // Trades Kite sends again are not changes: count only the keys that were new.
  let newTrades = 0;
  if (trades.length) {
    const keys = trades.map((t) => t.trade_key);
    const r = (await ctx.d1
      .prepare(`select trade_key from trades where trade_key in (${keys.map(() => "?").join(",")})`)
      .bind(...keys)
      .all()) as { results: unknown[] };
    newTrades = keys.length - r.results.length;
  }
  changes += newTrades;
  stmts.push(
    ctx.d1
      .prepare(
        "insert or replace into kite_syncs (account, source, fetched_at, trades, positions, margins, gtts, changes) values (?, ?, ?, ?, ?, ?, ?, ?)",
      )
      .bind(
        ACCOUNT,
        SOURCE,
        at,
        JSON.stringify(data.trades),
        JSON.stringify(data.positions),
        JSON.stringify(data.margins),
        JSON.stringify(data.gtts),
        changes,
      ),
    // Keep this snapshot and the one before it; older ones are history the lots maths does not read.
    ctx.d1
      .prepare(
        "delete from holdings where account = ? and source = ? and snapshot_at not in (select snapshot_at from (select distinct snapshot_at from holdings where account = ? and source = ? order by snapshot_at desc limit 2))",
      )
      .bind(ACCOUNT, SOURCE, ACCOUNT, SOURCE),
  );
  await ctx.d1.batch(stmts);
  return { fetchedAt: at, holdings: holdings.length, trades: trades.length, changes };
}

export type LastSync = {
  fetched_at: string;
  changes: number | null;
  holdings: number;
  trades: number;
};

export async function lastSync(ctx: Pick<Ctx, "d1">): Promise<LastSync | null> {
  const row = (await ctx.d1
    .prepare(
      "select fetched_at, changes, trades from kite_syncs where account = ? order by fetched_at desc limit 1",
    )
    .bind(ACCOUNT)
    .first()) as { fetched_at: string; changes: number | null; trades: string | null } | null;
  if (!row) return null;
  const h = (await ctx.d1
    .prepare(
      "select count(*) as n from holdings where account = ? and source = ? and snapshot_at = ?",
    )
    .bind(ACCOUNT, SOURCE, row.fetched_at)
    .first()) as { n: number };
  let trades = 0;
  try {
    trades = (JSON.parse(row.trades ?? "[]") as unknown[]).length;
  } catch {}
  return { fetched_at: row.fetched_at, changes: row.changes, holdings: h.n, trades };
}
