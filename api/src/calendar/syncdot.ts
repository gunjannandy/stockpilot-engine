// The Sync control's yellow dot (R4). The father logs into Kite himself and may skip it, so on a trading day the
// dot says "the holdings are from before today's open". Never on a weekend or a market holiday: the calendar decides.
import { type Calendar, isTradingDay, istDate } from "./calendar";

/** The market opens at 09:15 IST. */
export const MARKET_OPEN_IST = "09:15";

/**
 * True when `now` falls on a trading day and the last Sync (an IST text like `2026-11-27T18:00:00+05:30`)
 * was before that day's 09:15, or there has been none. It shows from midnight, not from 09:15: the holdings are
 * already a day old at breakfast, and the dot clears the moment he syncs (decision in the R4 commit).
 */
export function syncDot(cal: Calendar, syncedAt: string | null, now: Date): boolean {
  const today = istDate(now);
  if (!isTradingDay(cal, today).is_trading_day) return false;
  if (!syncedAt) return true;
  return syncedAt.slice(0, 16) < `${today}T${MARKET_OPEN_IST}`;
}
