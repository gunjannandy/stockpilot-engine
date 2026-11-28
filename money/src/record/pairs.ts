// His trades matched buy to sell (first in, first out, as `realise` does), each pair carrying the route that
// bought the lot. This is what the own record takes as input. A port of Python `book/pairs.py: load`; the
// matcher is `tax.realise`, so the tax screen and the record can never disagree about which lot a sale used.
import { canon } from "../core/kinds";
import { realise, type TaxLot, type TaxSale } from "../tax/tax";
import type { Pair } from "./record";

/** A stored lot plus the route that bought it (from the trade's tag: kite | smallcase | none known). */
export type RoutedLot = TaxLot & { route?: string | null };
export type PairSale = TaxSale & { kind: string };

const isInr = (x: { currency?: string | null }): boolean => (x.currency || "INR") === "INR";

/** Stock lots and sales in rupees only (funds and RSUs are a different question), matched first in, first out.
 *  `lots` come in the order the lots table gives them (acquired date, then id), `sales` by sold date, then id.
 *  A lot with no route (a bonus) takes the route of the first routed lot of that stock; else the father's own. */
export function buildPairs(lots: readonly RoutedLot[], sales: readonly PairSale[]): Pair[] {
  const stock = lots.filter((l) => canon(l.kind) === "equity" && isInr(l)).map((l) => ({ ...l }));
  const first = new Map<string, string>();
  for (const l of stock)
    if (l.route) if (!first.has(l.isin || l.symbol)) first.set(l.isin || l.symbol, l.route);
  for (const l of stock) if (!l.route) l.route = first.get(l.isin || l.symbol) ?? "kite";
  const byId = new Map(stock.map((l) => [l.id, l]));
  const own = sales.filter((s) => canon(s.kind) === "equity" && isInr(s));
  return realise(stock, own).map((row) => ({
    route: (byId.get(row.lot_id) as RoutedLot).route as string,
    symbol: row.symbol,
    acquiredOn: row.acquired_on,
    soldOn: row.sold_on,
    quantity: row.quantity,
    cost: row.cost,
    proceeds: row.proceeds,
    gain: row.gain,
  }));
}
