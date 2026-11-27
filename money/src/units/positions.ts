// What the account holds today. Quantity and cost come from the lots (built from the owners' documents);
// Kite and the CDSL statement are the check, and fill a holding the lots do not have yet (an IPO
// allotment, a demerger). Every reader of holdings reads them here. A port of Python `book/positions.py`.
//
// Two things come from outside because other tickets own them: the rule that dates the day a lot turns
// long term (the tax rules file, MONEYTAX) and the price of a unit on the day (the data plane, PORTFOLIO).
import { compareDays, type Day } from "../core/dates";
import { canon, isForeign } from "../core/kinds";
import { pyFixed, pySum } from "../core/round";
import { kiteHoldings } from "../lots/rebuild";
import type { KiteSnapshot } from "../lots/types";

export const DUST_INR = 1000.0; // a holding worth less than this is a leftover, not shown
export const FOREIGN_NAMES: Record<string, string> = { US81762P1021: "ServiceNow" }; // the only foreign share held

/** A row of the lots table. */
export type LotRow = {
  kind: string;
  symbol: string;
  isin: string | null;
  acquiredOn: Day;
  quantity: number;
  closedQuantity: number;
  costPerUnit: number;
  currency: string | null;
  estimated?: boolean | null;
};
export type StockRow = { symbol: string; name: string | null; isin: string | null };
export type FundRow = {
  schemeCode: number;
  name: string;
  plan: string;
  option: string;
  category: string | null;
  isinGrowth: string | null;
  isinReinvest: string | null;
};

export type OpenLot = {
  acquiredOn: Day;
  quantity: number; // still open
  cost: number | null; // rupees per unit (a US lot: dollars times the rate of its vest day)
  turnsLongTermOn: Day | null;
};

export type Position = {
  kind: string; // equity | mf | foreign
  symbol: string;
  isin: string | null;
  name: string;
  quantity: number;
  avgCost: number | null; // rupees per unit; null when no document gives a cost
  price: number | null; // rupees per unit on the day; null when no price is stored
  source: string; // lots | kite | statement
  lots: OpenLot[];
  check: string | null; // what Kite or the statement says when it differs from the lots
};

export const positionValue = (p: Position): number => p.quantity * (p.price || p.avgCost || 0);

export type FundInfo = { name: string; category: string | null };
export type LongTermQuery = {
  kind: string;
  isin: string | null;
  currency: string | null;
  acquiredOn: Day;
  fund: FundInfo | null;
};
export type PriceItem = { kind: string; symbol: string; isin: string | null };

export type HeldInput = {
  asOf: Day;
  lots: readonly LotRow[]; // ordered by acquired date, then id
  stocks: readonly StockRow[];
  funds: readonly FundRow[];
  kite: KiteSnapshot | null;
  statement: Record<string, number>; // the latest depository statement: ISIN -> units, units above zero
  rate: number | null; // USD/INR on `asOf`
  rateOn: (day: Day) => number | null; // USD/INR for any day (the SBI rate where there is one)
  /** The day a lot turns long term (`tax.turns_long_term_on` of its bucket); null for a bucket that never does. */
  turnsLongTermOn: (q: LongTermQuery) => Day | null;
  /** One unit's price in rupees on `asOf`, per item, in order; null where none is stored. */
  unitPrices: (
    items: PriceItem[],
    fundCodes: Record<string, number>,
    rate: number | null,
  ) => (number | null)[];
};

export const unitText = (n: number): string => {
  const t = pyFixed(n, 2);
  return t.includes(".") ? t.replace(/0+$/, "").replace(/\.$/, "") : t;
};
const u = unitText;

function fundsByIsin(funds: readonly FundRow[]): Map<string, FundRow> {
  const out = new Map<string, FundRow>();
  for (const f of funds) {
    for (const isin of [f.isinGrowth, f.isinReinvest]) if (isin && !out.has(isin)) out.set(isin, f);
  }
  return out;
}

function identity(stockRows: readonly StockRow[], fundRows: readonly FundRow[]) {
  const stocks = new Map<string, [string, string | null]>();
  for (const s of stockRows) if (s.isin) stocks.set(s.isin, [s.symbol, s.name]);
  const funds = new Map<string, string>();
  for (const f of fundRows) if (f.isinGrowth) funds.set(f.isinGrowth, f.name);
  return (kind: string, isin: string | null, fallback: string): [string, string] => {
    if (isin && isin in FOREIGN_NAMES) return [fallback, FOREIGN_NAMES[isin] as string];
    if (kind === "mf") return [isin || fallback, (isin ? funds.get(isin) : undefined) ?? fallback];
    const [symbol, name] = (isin ? stocks.get(isin) : undefined) ?? [fallback, null];
    return [symbol, name || (isin ? funds.get(isin) : undefined) || symbol];
  };
}

/** Kite's units win. Units the documents do not explain are costed so the total matches Kite's average;
 *  units the documents show beyond Kite's were sold without a document, and the oldest lots go first. */
function byKite(
  kiteQty: number,
  kiteAvg: number,
  lotQty: number,
  lots: OpenLot[],
  lotCost: number | null,
): { qty: number; cost: number | null; lots: OpenLot[]; source: string; check: string | null } {
  if (Math.abs(kiteQty - lotQty) < 1e-6)
    return { qty: kiteQty, cost: lotCost, lots, source: "lots", check: null };
  if (lotQty < kiteQty) {
    const gap = kiteQty - lotQty;
    let cost: number | null = kiteAvg;
    if (lotCost !== null && kiteAvg) {
      const rest = (kiteAvg * kiteQty - lotCost * lotQty) / gap;
      cost = (lotCost * lotQty + (rest > 0 ? rest : kiteAvg) * gap) / kiteQty;
    }
    return {
      qty: kiteQty,
      cost: cost !== null ? cost : lotCost,
      lots,
      source: "kite",
      check: `Documents explain ${u(lotQty)} of ${u(kiteQty)} units.`,
    };
  }
  let left = lotQty - kiteQty;
  const kept: OpenLot[] = [];
  for (const l of lots) {
    const cut = Math.min(l.quantity, left);
    left -= cut;
    if (l.quantity - cut > 1e-9) kept.push({ ...l, quantity: l.quantity - cut });
  }
  let cost: number | null = kiteAvg;
  if (kept.length && kept.every((l) => l.cost !== null)) {
    cost = pySum(kept.map((l) => l.quantity * (l.cost as number))) / kiteQty;
  }
  return {
    qty: kiteQty,
    cost,
    lots: kept,
    source: "lots",
    check: `Documents show ${u(lotQty)} units; Kite shows ${u(kiteQty)}.`,
  };
}

/** Drops a leftover worth under DUST_INR that only a depository statement knows (0.195 units of a liquid
 *  fund). A holding Kite or a document shows stays whatever its size, and one with no price is kept:
 *  a gap must never hide a holding. */
export function withoutDust(positions: readonly Position[]): Position[] {
  return positions.filter(
    (p) => p.source !== "statement" || p.price === null || positionValue(p) >= DUST_INR,
  );
}

type Group = {
  kind: string;
  symbol: string;
  isin: string | null;
  lots: OpenLot[];
  foreign: boolean;
  estimated: number;
};

export function held(input: HeldInput): Position[] {
  const ident = identity(input.stocks, input.funds);
  const funds = fundsByIsin(input.funds);
  const rate = input.rate;
  const grouped = new Map<string, Group>();
  for (const l of input.lots) {
    const qty = l.quantity - l.closedQuantity;
    if (!(qty > 1e-9)) continue;
    const cur = l.currency || "INR";
    const k = canon(l.kind);
    const gk = `${k}\u0000${l.isin || l.symbol}`;
    const g = grouped.get(gk) ?? {
      kind: k,
      symbol: l.symbol,
      isin: l.isin,
      lots: [],
      foreign: false,
      estimated: 0,
    };
    grouped.set(gk, g);
    g.estimated += l.estimated ? qty : 0.0;
    const foreign = isForeign({ kind: l.kind, currency: cur });
    g.foreign = g.foreign || foreign;
    let cost: number | null = l.costPerUnit;
    if (foreign) {
      // each lot at the rate of its own day; the nearest earlier rate, else today's, else no cost at all
      const dayRate = input.rateOn(l.acquiredOn) || rate;
      cost = dayRate ? cost * dayRate : null;
    }
    const fund = k === "mf" && l.isin ? (funds.get(l.isin) ?? null) : null;
    g.lots.push({
      acquiredOn: l.acquiredOn,
      quantity: qty,
      cost,
      turnsLongTermOn: input.turnsLongTermOn({
        kind: l.kind,
        isin: l.isin,
        currency: cur,
        acquiredOn: l.acquiredOn,
        fund: fund ? { name: fund.name, category: fund.category } : null,
      }),
    });
  }
  const kite = input.kite ? kiteHoldings(input.kite.rows) : new Map();
  const haveKite = kite.size > 0;
  const statement = input.statement;
  const haveStatement = Object.keys(statement).length > 0;
  const out: Position[] = [];
  const items: PriceItem[] = [];
  for (const [key, g] of grouped) {
    let lots = g.lots;
    let qty = pySum(lots.map((l) => l.quantity));
    let cost: number | null = lots.every((l) => l.cost !== null)
      ? pySum(lots.map((l) => l.quantity * (l.cost as number))) / qty
      : null;
    const [symbol, name] = ident(g.kind, g.isin, kite.get(key)?.symbol ?? g.symbol);
    let source = "lots";
    let check: string | null = null;
    if (haveKite && !g.foreign) {
      const k = kite.get(key);
      if (!k) continue; // Kite has no such holding: the nightly unit check names the gap
      const r = byKite(k.qty, k.avg, qty, lots, cost);
      qty = r.qty;
      cost = r.cost;
      lots = r.lots;
      source = r.source;
      check = r.check;
    } else if (
      !haveKite &&
      haveStatement &&
      g.isin &&
      g.isin in statement &&
      Math.abs((statement[g.isin] as number) - qty) > 1e-6
    ) {
      check = `The depository statement shows ${pyGeneral(statement[g.isin] as number)}.`;
    }
    if (g.estimated > 1e-9) {
      check = `${check ? `${check} ` : ""}Estimated: ${u(g.estimated)} units are not in a document yet; their cost is Kite's average price.`;
    }
    out.push({
      kind: g.kind,
      symbol,
      isin: g.isin,
      name,
      quantity: qty,
      avgCost: cost,
      price: null,
      source,
      lots,
      check,
    });
    items.push({ kind: g.kind, symbol: g.symbol, isin: g.isin });
  }
  for (const [key, k] of kite) {
    if (grouped.has(key)) continue;
    const [kind, kid] = key.split("\u0000") as [string, string];
    const isin = kid !== k.symbol || kind === "mf" ? kid : null;
    const [symbol, name] = ident(kind, isin, k.symbol);
    out.push({
      kind,
      symbol,
      isin,
      name,
      quantity: k.qty,
      avgCost: k.avg,
      price: null,
      source: "kite",
      lots: [],
      check: null,
    });
    items.push({ kind, symbol, isin });
  }
  const have = new Set(out.map((p) => p.isin));
  const shares = new Set(input.stocks.map((s) => s.isin).filter((i): i is string => Boolean(i)));
  for (const [isin, qty] of Object.entries(statement)) {
    // With no Kite snapshot the depository statement fills any gap. With one, only a fund Kite cannot see
    // (held at the depository, not in Coin) is added: a share or ETF Kite lacks was sold since the statement.
    if (
      !have.has(isin) &&
      (!haveKite || (isin.startsWith("INF") && funds.has(isin) && !shares.has(isin)))
    ) {
      const kind = isin.startsWith("INF") ? "mf" : "equity";
      const [symbol, name] = ident(kind, isin, isin);
      out.push({
        kind,
        symbol,
        isin,
        name,
        quantity: qty,
        avgCost: null,
        price: null,
        source: "statement",
        lots: [],
        check: null,
      });
      items.push({ kind, symbol, isin });
    }
  }
  const codes: Record<string, number> = {};
  for (const [isin, f] of funds) codes[isin] = f.schemeCode;
  const prices = input.unitPrices(items, codes, rate);
  out.forEach((p, i) => {
    p.price = prices[i] ?? null;
  });
  return withoutDust(out)
    .map((p, i) => ({ p, i }))
    .sort((a, b) => -positionValue(a.p) - -positionValue(b.p) || a.i - b.i)
    .map(({ p }) => p);
}

/** Python's `f"{x:g}"` for the statement check line (six significant digits). */
function pyGeneral(x: number): string {
  if (x === 0) return "0";
  const exp = Math.floor(Math.log10(Math.abs(x)));
  if (exp < -4 || exp >= 6) {
    const [m, e] = x.toExponential(5).split("e");
    const mant = (m as string).replace(/0+$/, "").replace(/\.$/, "");
    const n = Number(e);
    return `${mant}e${n < 0 ? "-" : "+"}${String(Math.abs(n)).padStart(2, "0")}`;
  }
  const s = x.toPrecision(6);
  return s.includes(".") ? s.replace(/0+$/, "").replace(/\.$/, "") : s;
}

export { compareDays };
