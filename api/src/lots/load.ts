// Reads the stored rows `rebuild` and `buildPairs` need, so no screen has to. Read-only: lots and sales are
// derived on every call and never written. Nothing here calls a broker.
import type { Day } from "../../../money/src/core/dates";
import { rebuild } from "../../../money/src/lots/rebuild";
import type {
  Action,
  FidelityHolding,
  FidelityStatementLot,
  KiteSnapshot,
  RateOn,
  RebuildResult,
  Trade,
} from "../../../money/src/lots/types";
import { buildPairs, type RoutedLot } from "../../../money/src/record/pairs";
import type { Pair } from "../../../money/src/record/record";
import type { D1Like } from "../app";

// biome-ignore lint/suspicious/noExplicitAny: D1 rows are untyped; each column is read once, below.
type Row = Record<string, any>;
const all = async (d1: D1Like, sql: string, ...args: unknown[]): Promise<Row[]> =>
  (
    (await d1
      .prepare(sql)
      .bind(...args)
      .all()) as { results?: Row[] }
  ).results ?? [];

export type LoadOptions = {
  /** USD/INR on or before a day. Without it Fidelity's statement rows are left out: they cannot be priced, and
   *  using them unpriced would drop the documents' vest lots with nothing in their place. */
  rateOn?: RateOn;
};

export async function loadRebuild(d1: D1Like, opts: LoadOptions = {}): Promise<RebuildResult> {
  const trades: Trade[] = (
    await all(
      d1,
      "select source, source_ref, kind, symbol, isin, side, trade_date, quantity, price, currency, status, trade_key from trades order by trade_date, rowid",
    )
  ).map((r) => ({
    source: r.source,
    sourceRef: r.source_ref,
    kind: r.kind,
    symbol: r.symbol,
    isin: r.isin,
    side: r.side,
    tradeDate: r.trade_date,
    quantity: r.quantity,
    price: r.price,
    currency: r.currency,
    status: r.status,
    tradeKey: r.trade_key,
  }));
  if (trades.length === 0) return { lots: [], sales: [], unmatchedSells: [] };

  const actions: Action[] = (
    await all(
      d1,
      `select a.symbol, a.isin, a.ex_date, a.kind, a.numerator, a.denominator, a.source,
              t.new_isin, t.new_symbol, t.cost_fraction, t.price
       from corporate_actions a
       left join action_terms t on t.symbol = a.symbol and t.ex_date = a.ex_date and t.kind = a.kind
       order by a.ex_date, a.symbol, a.kind`,
    )
  ).map((r) => ({
    symbol: r.symbol,
    isin: r.isin,
    exDate: r.ex_date,
    kind: r.kind,
    numerator: r.numerator,
    denominator: r.denominator,
    source: r.source,
    newIsin: r.new_isin,
    newSymbol: r.new_symbol,
    costFraction: r.cost_fraction,
    price: r.price,
  }));

  const latest = (
    await all(d1, "select max(snapshot_at) as at from holdings where source = 'kite'")
  )[0]?.at as string | null | undefined;
  const kite: KiteSnapshot | null = latest
    ? {
        at: latest.slice(0, 10) as Day,
        rows: (
          await all(
            d1,
            "select kind, symbol, isin, quantity, avg_price from holdings where source = 'kite' and snapshot_at = ?",
            latest,
          )
        ).map((r) => ({
          kind: r.kind,
          symbol: r.symbol,
          isin: r.isin,
          quantity: r.quantity,
          avgPrice: r.avg_price,
        })),
      }
    : null;

  const fidelityHoldings: FidelityHolding[] = (
    await all(
      d1,
      "select as_of, symbol, isin, quantity, cost_basis_inr from fidelity_holdings order by as_of, symbol",
    )
  ).map((r) => ({
    asOf: r.as_of,
    symbol: r.symbol,
    isin: r.isin,
    quantity: r.quantity,
    costBasisInr: r.cost_basis_inr,
  }));
  const fidelityLots: FidelityStatementLot[] = (
    await all(
      d1,
      "select as_of, symbol, isin, acquired_on, quantity, cost_basis_inr from fidelity_lots order by as_of, symbol, acquired_on",
    )
  ).map((r) => ({
    asOf: r.as_of,
    symbol: r.symbol,
    isin: r.isin,
    acquiredOn: r.acquired_on,
    quantity: r.quantity,
    costBasisInr: r.cost_basis_inr,
  }));

  const priced = Boolean(opts.rateOn);
  return rebuild({
    trades,
    actions,
    kite,
    rateOn: opts.rateOn,
    fidelityHoldings: priced ? fidelityHoldings : [],
    fidelityLots: priced ? fidelityLots : [],
  });
}

/** His rupee stock trades matched buy to sell, each pair carrying the route that bought the lot. */
export async function loadPairs(d1: D1Like, opts: LoadOptions = {}): Promise<Pair[]> {
  const built = await loadRebuild(d1, opts);
  if (built.lots.length === 0) return [];
  const route = new Map<string, string>();
  for (const r of await all(
    d1,
    "select trade_key, placed_by from trade_tags where placed_by is not null",
  ))
    route.set(r.trade_key, r.placed_by);
  const lots: RoutedLot[] = built.lots.map((l, i) => ({
    id: i + 1,
    symbol: l.symbol,
    isin: l.isin ?? l.symbol,
    kind: l.kind,
    acquired_on: l.acquiredOn,
    quantity: l.quantity,
    cost_per_unit: l.costPerUnit,
    currency: l.currency,
    route: route.get(l.sourceRef) ?? null,
  }));
  const sales = built.sales.map((s) => ({
    symbol: s.symbol,
    isin: s.isin ?? s.symbol,
    kind: s.kind,
    sold_on: s.soldOn,
    quantity: s.quantity,
    price_per_unit: s.pricePerUnit,
    currency: s.currency,
  }));
  return buildPairs(lots, sales);
}
