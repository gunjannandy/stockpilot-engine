// Fidelity's two documents turned into lots: the "Current Shares" statement (real lots, in rupees) and the
// Stock Plan holding (one estimated lot for the shares no document explains). A port of the Python
// `trades/lots.py: _statement_lots, _fidelity_gap_lots`: same order, same rounding, same float arithmetic.
import { compareDays } from "../core/dates";
import { pyRound, pySum } from "../core/round";
import { sell } from "./fifo";
import type { FidelityHolding, FidelityStatementLot, Lot, RateOn, Trade } from "./types";

const r6 = (x: number): number => pyRound(x, 6);
const byText = (a: string, b: string): number => (a < b ? -1 : a > b ? 1 : 0);

/** The statement's lots replace the documents' lots of that holding up to the statement day (a document dates a
 *  vest by its delivery, the statement by its vest day). Later vests stay from the documents; later sales close
 *  the statement's lots first in, first out. The cost per share is in dollars at the day's rate, so the units
 *  times that cost times the same rate give Fidelity's rupee cost back. */
export function statementLots(
  built: Lot[],
  rows: readonly FidelityStatementLot[],
  trades: readonly Trade[],
  rateOn: RateOn,
): Lot[] {
  const latest = new Map<string, string>();
  for (const r of rows) {
    const seen = latest.get(r.symbol);
    if (seen === undefined || compareDays(r.asOf, seen) > 0) latest.set(r.symbol, r.asOf);
  }
  const current = rows
    .filter((r) => r.asOf === latest.get(r.symbol))
    .sort((a, b) => byText(a.symbol, b.symbol) || compareDays(a.acquiredOn, b.acquiredOn));
  if (!current.length) return built;
  const rate = rateOn ?? (() => null);
  let out = built;
  for (const symbol of [...new Set(current.map((r) => r.symbol))].sort(byText)) {
    const mine = current.filter((r) => r.symbol === symbol);
    const { asOf, isin } = mine[0] as FidelityStatementLot;
    const isMine = (l: Lot) => l.kind === "rsu" && (l.symbol === symbol || l.isin === isin);
    out = out.filter((l) => !(isMine(l) && compareDays(l.on, asOf) <= 0));
    const fresh: Lot[] = [];
    for (const r of mine) {
      const rt = rate(r.acquiredOn);
      if (rt) {
        fresh.push({
          kind: "rsu",
          symbol,
          isin,
          on: r.acquiredOn,
          qty: r.quantity,
          cost: r.costBasisInr / r.quantity / rt,
          closed: 0.0,
          cur: "USD",
          src: "fidelity_statement",
          ref: `statement:${asOf}:${r.acquiredOn}`,
        });
      }
    }
    // a SQL `isin = NULL` never matches, so a missing ISIN matches on the symbol alone
    const later = trades
      .map((t, i) => ({ t, i }))
      .filter(
        ({ t }) =>
          t.kind === "rsu" &&
          t.side === "sell" &&
          (t.status ?? "confirmed") === "confirmed" &&
          (t.symbol === symbol || (isin !== null && t.isin === isin)) &&
          compareDays(t.tradeDate, asOf) > 0,
      )
      .sort((a, b) => compareDays(a.t.tradeDate, b.t.tradeDate) || a.i - b.i);
    for (const { t } of later) sell(fresh, t.quantity);
    out = out.concat(fresh);
  }
  return out;
}

/** Vests after the last document are missing from `built`; the shares beyond it become one estimated lot dated
 *  the latest Stock Plan statement, priced so the whole holding costs what Fidelity says. A later vest document
 *  replaces it on the next rebuild. */
export function fidelityGapLots(
  built: readonly Lot[],
  holdings: readonly FidelityHolding[],
  rateOn: RateOn,
): Lot[] {
  if (!holdings.length) return [];
  let newest = (holdings[0] as FidelityHolding).asOf;
  for (const h of holdings) if (compareDays(h.asOf, newest) > 0) newest = h.asOf;
  const rate = rateOn ?? (() => null);
  const out: Lot[] = [];
  const rows = holdings.filter((h) => h.asOf === newest).sort((a, b) => byText(a.symbol, b.symbol));
  for (const { asOf, symbol, isin, quantity, costBasisInr } of rows) {
    const mine = built.filter(
      (l) => l.kind === "rsu" && (l.symbol === symbol || (isin && l.isin === isin)),
    );
    const have = pySum(mine.map((l) => l.qty - l.closed));
    const gap = quantity - have;
    const nowRate = rate(asOf);
    if (gap <= 0.0005 || !nowRate) continue;
    const paid = pySum(mine.map((l) => (l.qty - l.closed) * l.cost * (rate(l.on) || nowRate)));
    const rest = costBasisInr ? costBasisInr - paid : 0.0;
    if (!(rest > 0)) continue;
    out.push({
      kind: "rsu",
      symbol,
      isin,
      on: asOf,
      qty: r6(gap),
      cost: rest / gap / nowRate,
      closed: 0.0,
      cur: "USD",
      src: "estimated",
      ref: `estimated:fidelity:${asOf}`,
      estimated: true,
    });
  }
  return out;
}
