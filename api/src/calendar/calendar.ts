// The one market calendar and corporate-action module (decisions §2 Schedules, story 117/118).
// Pure functions over a list of rows; the rows come from the `calendar` dataset's current run.
// Dates are plain `YYYY-MM-DD` text in IST; instants are UTC `Date`s shown in IST by `istText`.
import type { CalendarEntry } from "@stockpilot/contract";

export type Calendar = { rows: CalendarEntry[] };
export type DayStatus = { is_trading_day: boolean; reason: string | null };

/** NSE and BSE close at 15:30 IST; the promise is that the close is in by 08:30 IST next morning. */
export const CLOSE_DUE_HOUR_IST = 8.5;
const IST_MS = 5.5 * 3600 * 1000;
const DAY_MS = 86_400_000;

const toMs = (date: string) => Date.parse(`${date}T00:00:00Z`);
const fromMs = (ms: number) => new Date(ms).toISOString().slice(0, 10);
export const addDays = (date: string, n: number) => fromMs(toMs(date) + n * DAY_MS);
const weekday = (date: string) => new Date(toMs(date)).getUTCDay();

export function isTradingDay(cal: Calendar, date: string): DayStatus {
  const holiday = cal.rows.find((r) => r.kind === "holiday" && r.date === date);
  if (holiday && "reason" in holiday) return { is_trading_day: false, reason: holiday.reason };
  if (cal.rows.some((r) => r.kind === "special" && r.date === date))
    return { is_trading_day: true, reason: null };
  const wd = weekday(date);
  return wd === 0 || wd === 6
    ? { is_trading_day: false, reason: "Weekend" }
    : { is_trading_day: true, reason: null };
}

/** The latest trading day on or before `date`. */
export function lastTradingDay(cal: Calendar, date: string): string {
  let d = date;
  for (let i = 0; i < 400; i++, d = addDays(d, -1))
    if (isTradingDay(cal, d).is_trading_day) return d;
  return date;
}

/** The first trading day after `date`. */
export function nextTradingDay(cal: Calendar, date: string): string {
  let d = addDays(date, 1);
  for (let i = 0; i < 400; i++, d = addDays(d, 1))
    if (isTradingDay(cal, d).is_trading_day) return d;
  return d;
}

/** The IST calendar day of an instant. */
export const istDate = (now: Date) => fromMs(now.getTime() + IST_MS);

/**
 * The trading day whose close should be in by `now`: the latest trading day D whose deadline
 * (08:30 IST on the next calendar day) has passed. Holidays and weekends do not move the deadline.
 */
export function expectedAsOf(cal: Calendar, now: Date): string {
  const ist = new Date(now.getTime() + IST_MS);
  const minutes = ist.getUTCHours() * 60 + ist.getUTCMinutes();
  const today = fromMs(Date.UTC(ist.getUTCFullYear(), ist.getUTCMonth(), ist.getUTCDate()));
  // Today's own close is due tomorrow morning, so the latest candidate is yesterday; before today's
  // 08:30 even yesterday's is not yet due, so the candidate is the day before.
  const latest = minutes >= CLOSE_DUE_HOUR_IST * 60 ? addDays(today, -1) : addDays(today, -2);
  return lastTradingDay(cal, latest);
}

/** Fresh = the last trading day's close is in. `asOf` is the dataset's as-of date. */
export const isFresh = (cal: Calendar, asOf: string, now: Date) => asOf >= expectedAsOf(cal, now);

// ---- corporate actions ---------------------------------------------------------------------------------

const actionsFor = (cal: Calendar, symbol: string) =>
  cal.rows.filter((r) => "symbol" in r && r.symbol === symbol);

/**
 * What to multiply a price quoted on `onDate` by so it compares with today's prices: every split and
 * bonus whose ex-date is after `onDate` scales it. A split 1 -> n divides by n; a bonus n for every o
 * held divides by (o + n) / o.
 */
export function adjustmentFactor(cal: Calendar, symbol: string, onDate: string): number {
  let factor = 1;
  for (const a of actionsFor(cal, symbol)) {
    if (a.date <= onDate) continue;
    if (a.kind === "split") factor *= a.old_shares / a.new_shares;
    else if (a.kind === "bonus") factor *= a.old_shares / (a.old_shares + a.new_shares);
  }
  return factor;
}

export const adjustedPrice = (cal: Calendar, symbol: string, price: number, onDate: string) =>
  Math.round(price * adjustmentFactor(cal, symbol, onDate) * 1e6) / 1e6;

/** The symbol a name goes by now, following symbol changes (chains included). */
export function currentSymbol(cal: Calendar, symbol: string): string {
  let s = symbol;
  for (let i = 0; i < 10; i++) {
    const change = cal.rows
      .filter((r) => r.kind === "symbol_change" && r.symbol === s)
      .sort((a, b) => a.date.localeCompare(b.date))
      .at(-1);
    if (!change || change.kind !== "symbol_change") return s;
    s = change.new_symbol;
  }
  return s;
}

export const isDelisted = (cal: Calendar, symbol: string, onDate: string) =>
  actionsFor(cal, symbol).some((a) => a.kind === "delisting" && a.date <= onDate);

// ---- health ---------------------------------------------------------------------------------------------

/** Days from `today` to the last day the calendar lists a holiday or special session for. */
export function daysCovered(cal: Calendar, today: string): { until: string | null; ahead: number } {
  const dates = cal.rows
    .filter((r) => r.kind === "holiday" || r.kind === "special")
    .map((r) => r.date);
  const until = dates.sort().at(-1) ?? null;
  return { until, ahead: until ? Math.round((toMs(until) - toMs(today)) / DAY_MS) : 0 };
}
