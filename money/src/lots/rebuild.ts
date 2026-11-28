// Trades in, lots out. Lots are derived: `rebuild` replays every confirmed trade and corporate action
// in date order (FIFO per ISIN) and returns the lots and sales it owns, so it is idempotent and a
// late-arriving document or corporate action fixes history on the next rebuild. A line-for-line
// port of the Python `trades/lots.py`: same order of events, same rounding, same float arithmetic.
import { compareDays, type Day } from "../core/dates";
import { canon, isForeign } from "../core/kinds";
import { pyProd, pyRound, pySum } from "../core/round";
import { fidelityGapLots, statementLots } from "./fidelity";
import { EPS, sell } from "./fifo";
import type {
  Action,
  Holding,
  KiteRow,
  KiteSnapshot,
  Lot,
  RebuildInput,
  RebuildResult,
  Sale,
  StoredLot,
  Trade,
} from "./types";

export const OWNED = "trades:";

export const r6 = (x: number): number => pyRound(x, 6);
const or = <T>(a: T | null | undefined, b: T): T => (a ? a : b);

/** Python's `f"{x:g}"`. */
function fmtG(x: number): string {
  if (x === 0) return "0";
  const exp = Math.floor(Math.log10(Math.abs(x)));
  let s = x.toPrecision(6);
  if (exp < -4 || exp >= 6) {
    const [m, e] = x.toExponential(5).split("e");
    const mant = (m as string).includes(".")
      ? (m as string).replace(/0+$/, "").replace(/\.$/, "")
      : m;
    const n = Number(e);
    return `${mant}e${n < 0 ? "-" : "+"}${String(Math.abs(n)).padStart(2, "0")}`;
  }
  if (s.includes(".")) s = s.replace(/0+$/, "").replace(/\.$/, "");
  return s;
}

/** Python's `repr(float)` for the cases trade prices take. */
function reprFloat(x: number | null): string {
  if (x === null) return "None";
  return Number.isInteger(x) && Math.abs(x) < 1e16 ? `${x}.0` : String(x);
}

/** The key a trade is saved under: the exchange trade id, else a content key. */
export function tradeKey(t: Trade): string {
  if (t.tradeKey) return t.tradeKey;
  return `${t.isin || t.symbol}|${t.tradeDate}|${t.side}|${fmtG(t.quantity)}|${reprFloat(t.price)}`;
}

/** `save_trades`: keep the first trade seen under each key. */
export function dedupeTrades(trades: readonly Trade[]): Trade[] {
  const seen = new Set<string>();
  const out: Trade[] = [];
  for (const t of trades) {
    const k = tradeKey(t);
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(t);
  }
  return out;
}

const SERIES = /\s*-\s*(A|B|T|X|Z|BE|BZ|EQ|XT)$/;

export function company(symbol: string | null | undefined): string {
  return (symbol ?? "").replace(SERIES, "").trim();
}

type Row = {
  source: string;
  sourceRef: string;
  kind: string;
  symbol: string;
  isin: string | null;
  side: string;
  date: Day;
  qty: number;
  price: number;
  cur: string;
  key: string;
};

type Event =
  | { typ: "trade"; when: Day; rank: number; row: Row }
  | { typ: "action"; when: Day; rank: number; act: Action };

type Open = Lot;
type Sold = {
  kind: string;
  symbol: string;
  isin: string | null;
  when: Day;
  qty: number;
  price: number;
  cur: string;
  src: string;
  ref: string;
};

function oneCompanyOneKey(rows: Row[], current: Record<string, string>): Row[] {
  const parent = new Map<string, string>();
  const find = (x: string): string => {
    let cur = x;
    for (;;) {
      const p = parent.get(cur);
      if (p === undefined) {
        parent.set(cur, cur);
        return cur;
      }
      if (p === cur) return cur;
      const gp = parent.get(p) as string;
      parent.set(cur, gp);
      cur = gp;
    }
  };
  for (const r of rows) {
    if (r.kind === "stock" && r.isin) {
      const a = find(`i:${r.isin}`);
      const b = find(`s:${company(r.symbol)}`);
      parent.set(a, b);
    }
  }
  const name = new Map<string, [string, string | null]>();
  for (const r of rows) {
    if (r.kind === "stock") {
      const root = find(`s:${company(r.symbol)}`);
      const sym = company(r.symbol);
      const prior = name.get(root);
      name.set(root, [sym, or(current[sym], or(r.isin, prior ? prior[1] : null))]);
    }
  }
  return rows.map((r) => {
    if (r.kind !== "stock") return r;
    const [sym, isin] = name.get(find(`s:${company(r.symbol)}`)) as [string, string | null];
    return { ...r, symbol: sym, isin };
  });
}

function demergerReady(a: Action): boolean {
  return (
    a.kind === "demerger" &&
    Boolean(a.newIsin && a.newSymbol) &&
    a.costFraction !== null &&
    a.costFraction !== undefined &&
    Boolean(a.denominator)
  );
}

const heldOf = (open: Open[], exDate: Day): number =>
  pySum(open.filter((l) => compareDays(l.on, exDate) < 0).map((l) => l.qty - l.closed));

function applyAction(open: Open[], a: Action, exDate: Day, spawned: Map<string, Open[]>): void {
  const num = a.numerator;
  const den = a.denominator;
  if (a.kind === "split") {
    const m = num / den;
    for (const lot of open) {
      if (compareDays(lot.on, exDate) < 0) {
        lot.qty *= m;
        lot.closed *= m;
        lot.cost /= m;
      }
    }
  } else if (a.kind === "bonus" && open.length) {
    const held = heldOf(open, exDate);
    const free = Math.floor((held * num) / den + EPS);
    if (free > 0) {
      const base = open[0] as Open;
      open.push({ ...base, on: exDate, qty: free, cost: 0.0, closed: 0.0, ref: `bonus:${exDate}` });
    }
  } else if (a.kind === "demerger" && demergerReady(a)) {
    const newSymbol = a.newSymbol as string;
    const costFraction = a.costFraction as number;
    for (const lot of open) {
      const left = lot.qty - lot.closed;
      if (compareDays(lot.on, exDate) < 0 && left > EPS) {
        const newQty = (left * num) / den;
        const list = spawned.get(newSymbol) ?? [];
        spawned.set(newSymbol, list);
        list.push({
          kind: lot.kind,
          symbol: newSymbol,
          isin: a.newIsin ?? null,
          on: lot.on,
          qty: newQty,
          cost: (lot.cost * costFraction) / (num / den),
          closed: 0.0,
          cur: lot.cur,
          src: "demerger",
          ref: `demerger:${exDate}`,
        });
        lot.cost *= 1 - costFraction;
      }
    }
  } else if (
    a.kind === "rights" &&
    open.length &&
    a.price &&
    (a.source === undefined ? "nse" : a.source) !== "nse"
  ) {
    const held = heldOf(open, exDate);
    const added = Math.floor((held * num) / den + EPS);
    if (added > 0) {
      open.push({
        ...(open[0] as Open),
        on: exDate,
        qty: added,
        cost: a.price,
        closed: 0.0,
        src: "rights",
        ref: `rights:${exDate}`,
      });
    }
  }
}

/** Units Kite shows that the documents do not explain become one lot per holding, at Kite's average
 *  price and dated its snapshot, marked estimated; the next rebuild finds a later document's units
 *  already in `built` and adds less, so a document always replaces the estimate. */
function estimatedLots(
  built: Open[],
  kite: KiteSnapshot | null | undefined,
  fidelityHoldings: RebuildInput["fidelityHoldings"],
  rateOn: RebuildInput["rateOn"],
): Open[] {
  const gap = fidelityGapLots(built, fidelityHoldings ?? [], rateOn);
  if (!kite) return gap;
  const have = new Map<string, number>();
  for (const lot of built) {
    if (!isForeign({ kind: lot.kind, currency: lot.cur })) {
      const key = `${canon(lot.kind)}|${lot.isin || lot.symbol}`;
      have.set(key, (have.get(key) ?? 0) + lot.qty - lot.closed);
    }
  }
  const out: Open[] = gap;
  const entries = [...kiteHoldings(kite.rows).entries()].sort((a, b) =>
    pyTupleStr(a[0]) < pyTupleStr(b[0]) ? -1 : pyTupleStr(a[0]) > pyTupleStr(b[0]) ? 1 : 0,
  );
  for (const [key, { symbol, qty, avg }] of entries) {
    const [kind, ident] = splitKey(key);
    const gap = qty - (have.get(`${kind === "equity" ? "equity" : kind}|${ident}`) ?? 0.0);
    if (gap > 0.0005 && avg) {
      const isin = ident !== symbol || kind === "mf" ? ident : null;
      out.push({
        kind: kind === "mf" ? "mf" : "stock",
        symbol,
        isin,
        on: kite.at,
        qty: r6(gap),
        cost: avg,
        closed: 0.0,
        cur: "INR",
        src: "estimated",
        ref: `estimated:${kite.at}`,
        estimated: true,
      });
    }
  }
  return out;
}

const KEY_SEP = "\u0000";
const splitKey = (k: string): [string, string] => k.split(KEY_SEP) as [string, string];
const pyTupleStr = (k: string): string => {
  const [a, b] = splitKey(k);
  return `('${a}', '${b}')`;
};

/** `positions._kite`: the latest snapshot as {(canon kind, isin or symbol) -> (symbol, units, average)}. */
export function kiteHoldings(
  rows: readonly KiteRow[],
): Map<string, { symbol: string; qty: number; avg: number }> {
  const groups = new Map<
    string,
    { kind: string; symbol: string; isin: string | null; q: number; qa: number }
  >();
  for (const r of rows) {
    if (!(r.quantity > 0)) continue;
    const k = [r.kind, r.symbol, r.isin ?? ""].join(KEY_SEP) + (r.isin === null ? "N" : "S");
    const g = groups.get(k) ?? { kind: r.kind, symbol: r.symbol, isin: r.isin, q: 0, qa: 0 };
    g.q += r.quantity;
    g.qa += r.quantity * r.avgPrice;
    groups.set(k, g);
  }
  const out = new Map<string, { symbol: string; qty: number; avg: number }>();
  for (const g of groups.values()) {
    out.set([canon(g.kind), g.isin || g.symbol].join(KEY_SEP), {
      symbol: g.symbol,
      qty: g.q,
      avg: g.qa / g.q,
    });
  }
  return out;
}

export function rebuild(input: RebuildInput): RebuildResult {
  const stocks = input.stocks ?? {};
  const trades = input.trades
    .map((t, i) => ({ t, i }))
    .filter(
      ({ t }) =>
        (t.status ?? "confirmed") === "confirmed" &&
        ["buy", "sell", "vest"].includes(t.side) &&
        t.price !== null &&
        t.price !== undefined,
    )
    .sort((a, b) => compareDays(a.t.tradeDate, b.t.tradeDate) || a.i - b.i)
    .map(({ t }) => t);
  let rows: Row[] = trades.map((t) => ({
    source: t.source,
    sourceRef: t.sourceRef,
    kind: t.kind,
    symbol: t.symbol,
    isin: t.isin,
    side: t.side,
    date: t.tradeDate,
    qty: t.quantity,
    price: t.price as number,
    cur: t.currency ?? "INR",
    key: tradeKey(t),
  }));
  const actions = [...input.actions].sort((a, b) => compareDays(a.exDate, b.exDate));

  rows = oneCompanyOneKey(rows, stocks);
  const groups = new Map<string, Event[]>();
  for (const r of rows) {
    const key = r.kind === "stock" ? r.symbol : or(r.isin, r.symbol);
    const list = groups.get(key) ?? [];
    groups.set(key, list);
    list.push({ typ: "trade", when: r.date, rank: r.side === "sell" ? 1 : 0, row: r });
  }
  for (const a of actions) {
    const key = a.isin && groups.has(a.isin) ? a.isin : company(a.symbol);
    const list = groups.get(key);
    if (list) list.push({ typ: "action", when: a.exDate, rank: -1, act: a });
  }

  const children = new Set<string>();
  for (const a of actions)
    if (demergerReady(a) && groups.has(company(a.symbol))) children.add(a.newSymbol as string);
  for (const c of children) if (!groups.has(c)) groups.set(c, []);
  const spawned = new Map<string, Open[]>();
  const order = [...groups.keys()]
    .filter((k) => !children.has(k))
    .concat([...groups.keys()].filter((k) => children.has(k)));

  const unmatched: [string, Day, number][] = [];
  let out: Open[] = [];
  const sold: Sold[] = [];
  for (const key of order) {
    const events = groups.get(key) as Event[];
    const splits: [Day, number][] = [];
    for (const e of events) {
      if (e.typ === "action" && e.act.kind === "split")
        splits.push([e.act.exDate, e.act.numerator / e.act.denominator]);
    }
    // on one day: corporate action first (trades on the ex-date are at post-action prices), buys, then sells
    const sorted = events
      .map((e, i) => ({ e, i }))
      .sort((a, b) => compareDays(a.e.when, b.e.when) || a.e.rank - b.e.rank || a.i - b.i)
      .map(({ e }) => e);
    const open: Open[] = (spawned.get(key) ?? []).slice();
    for (const ev of sorted) {
      if (ev.typ === "action") {
        applyAction(open, ev.act, ev.when, spawned);
      } else if (ev.row.side === "sell") {
        const row = ev.row;
        const left = sell(open, row.qty);
        if (left > EPS) unmatched.push([or(row.isin, row.symbol), ev.when, r6(left)]);
        if (row.qty - left > EPS) {
          const m = pyProd(splits.filter(([ex]) => compareDays(ex, ev.when) > 0).map(([, r]) => r));
          sold.push({
            kind: row.kind,
            symbol: row.symbol,
            isin: row.isin,
            when: ev.when,
            qty: (row.qty - left) * m,
            price: row.price / m,
            cur: row.cur,
            src: row.source,
            ref: row.key,
          });
        }
      } else {
        const row = ev.row;
        open.push({
          kind: row.kind,
          symbol: row.symbol,
          isin: row.isin,
          on: ev.when,
          qty: row.qty,
          cost: row.price,
          closed: 0.0,
          cur: row.cur,
          src: row.source,
          ref: row.key,
        });
      }
    }
    out.push(...open);
  }
  out = statementLots(out, input.fidelityLots ?? [], input.trades, input.rateOn);
  out.push(...estimatedLots(out, input.kite, input.fidelityHoldings, input.rateOn));

  const lots: StoredLot[] = out.map((lot) => ({
    kind: lot.kind,
    symbol: lot.symbol,
    isin: lot.isin,
    acquiredOn: lot.on,
    quantity: r6(lot.qty),
    costPerUnit: r6(lot.cost),
    currency: lot.cur,
    closedQuantity: r6(lot.closed),
    source: `${OWNED}${lot.src}`,
    sourceRef: lot.ref,
    estimated: lot.estimated ?? false,
  }));
  const sales: Sale[] = sold.map((s) => ({
    kind: s.kind,
    symbol: s.symbol,
    isin: s.isin,
    soldOn: s.when,
    quantity: r6(s.qty),
    pricePerUnit: r6(s.price),
    currency: s.cur,
    source: `${OWNED}${s.src}`,
    sourceRef: s.ref,
  }));
  return { lots, sales, unmatchedSells: unmatched };
}

/** What the lots say is held now: remaining quantity and weighted average cost per kind, symbol, ISIN and currency. */
export function holdings(lots: readonly StoredLot[]): Holding[] {
  const groups = new Map<
    string,
    { kind: string; symbol: string; isin: string | null; cur: string; q: number; cost: number }
  >();
  for (const l of lots) {
    const k = [l.kind, l.symbol, l.isin ?? "\u0001", l.currency].join(KEY_SEP);
    const g = groups.get(k) ?? {
      kind: l.kind,
      symbol: l.symbol,
      isin: l.isin,
      cur: l.currency,
      q: 0,
      cost: 0,
    };
    const left = l.quantity - l.closedQuantity;
    g.q += left;
    g.cost += left * l.costPerUnit;
    groups.set(k, g);
  }
  return [...groups.values()]
    .filter((g) => g.q > 0.0000005)
    .sort((a, b) => (a.symbol < b.symbol ? -1 : a.symbol > b.symbol ? 1 : 0))
    .map((g) => ({
      kind: g.kind,
      symbol: g.symbol,
      isin: g.isin,
      quantity: r6(g.q),
      avgCost: r6(g.cost / g.q),
      currency: g.cur,
    }));
}
