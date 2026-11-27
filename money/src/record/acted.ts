// Which calls the owners acted on. A buy of a stock within 5 trading days after a buy call on it (a sell
// after a sell or trim call likewise), seen in contract notes or in Kite trades, marks the call acted on
// that trade's day. It feeds his own record and the month's budget left; it never reaches a forecast.
// A port of Python `book/acted.py`: it never moves a date already set.
import { addDays, compareDays, type Day, weekday } from "../core/dates";

export const WINDOW = 5; // trading days after the call

const CALL_SIDE: Record<string, string> = { buy: "buy", add: "buy", sell: "sell", trim: "sell" };

export type OpenCall = {
  id: number;
  symbol: string;
  madeOn: Day;
  /** coalesce(section, action) */
  kind: string | null;
};
export type DatedTrade = { symbol: string; side: string; tradeDate: Day };
/** A row of Kite's `trades` list as the sync stored it. */
export type KiteTrade = {
  tradingsymbol?: string | null;
  transaction_type?: unknown;
  fill_timestamp?: string | null;
  order_timestamp?: string | null;
  exchange_timestamp?: string | null;
};

/** Trading days in (first, last]: weekdays that are not NSE holidays. */
export function tradingDaysBetween(first: Day, last: Day, holidays: ReadonlySet<Day>): number {
  let n = 0;
  let d = first;
  while (compareDays(d, last) < 0) {
    d = addDays(d, 1);
    if (weekday(d) < 5 && !holidays.has(d)) n += 1;
  }
  return n;
}

const ISO_DAY = /^(\d{4}-\d{2}-\d{2})(?:[T ]\d{2}(?::\d{2}(?::\d{2})?)?)?$/;

/** (symbol, side, day) from the stored Kite syncs; Kite lists only the day's trades, so every sync is read. */
export function kiteTrades(syncs: readonly (readonly KiteTrade[] | null)[]): DatedTrade[] {
  const out: DatedTrade[] = [];
  for (const trades of syncs) {
    for (const t of trades ?? []) {
      const when = t.fill_timestamp || t.order_timestamp || t.exchange_timestamp;
      const side = String(t.transaction_type ?? "").toLowerCase();
      if (!t.tradingsymbol || !(side === "buy" || side === "sell") || !when) continue;
      const m = ISO_DAY.exec(String(when).slice(0, 19));
      if (!m) continue;
      out.push({ symbol: String(t.tradingsymbol).toUpperCase(), side, tradeDate: m[1] as Day });
    }
  }
  return out;
}

/** The days of each (symbol, side), oldest first, each only once. */
function byKey(trades: readonly DatedTrade[]): Map<string, Day[]> {
  const seen = new Set<string>();
  const unique: DatedTrade[] = [];
  for (const t of trades) {
    const k = `${t.symbol}\u0000${t.side}\u0000${t.tradeDate}`;
    if (!seen.has(k)) {
      seen.add(k);
      unique.push(t);
    }
  }
  unique.sort((a, b) => compareDays(a.tradeDate, b.tradeDate));
  const by = new Map<string, Day[]>();
  for (const t of unique) {
    const k = `${t.symbol}\u0000${t.side}`;
    const list = by.get(k) ?? [];
    by.set(k, list);
    list.push(t.tradeDate);
  }
  return by;
}

/** The calls (by id) that a matching trade followed within the window, and the day of that trade. */
export function mark(input: {
  openCalls: readonly OpenCall[]; // calls with no acted_on yet, in id order
  confirmedTrades: readonly DatedTrade[]; // status confirmed, buy or sell, side lower-cased
  kite: readonly DatedTrade[];
  holidays: ReadonlySet<Day>;
}): { id: number; actedOn: Day }[] {
  const trades = byKey([...input.confirmedTrades, ...input.kite]);
  const out: { id: number; actedOn: Day }[] = [];
  for (const call of input.openCalls) {
    const side = CALL_SIDE[call.kind ?? ""];
    if (!side) continue;
    for (const day of trades.get(`${call.symbol}\u0000${side}`) ?? []) {
      if (
        compareDays(day, call.madeOn) > 0 &&
        tradingDaysBetween(call.madeOn, day, input.holidays) <= WINDOW
      ) {
        out.push({ id: call.id, actedOn: day });
        break;
      }
    }
  }
  return out;
}
