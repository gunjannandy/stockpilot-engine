// Turns the watchlist answer into the rows the shared list page draws. Pure, so it is tested without a screen.
import type { CallView, WatchlistResponse } from "@stockpilot/contract";
import type { StockView, Verdict } from "../_kit/pending";

/** The call's verdict in the list page's five groups. Trim sits with Weak (both read "Trim" on screen). */
export function verdictOf(call: CallView | null): Verdict {
  switch (call?.verdict) {
    case "Sell":
      return "sell";
    case "Weak":
    case "Trim":
      return "weak";
    case "Buy":
      return "buy";
    case "Hold":
      return "keep";
    default:
      return "watch";
  }
}

/** One stock on the list. A stock with no call, or "No view yet", is shown as Watch with an empty meter. */
export function rowOf(i: WatchlistResponse["items"][number]): StockView {
  const call = i.call;
  return {
    id: i.id,
    name: i.name ?? i.id,
    symbol: i.id,
    sector: "",
    exchange: call?.exchange ?? "NSE",
    verdict: verdictOf(call),
    strength: call?.chance == null ? 0 : Math.round(call.chance * 100),
    trades: [],
    ageSeconds: 0,
  };
}

export const stockRows = (d: WatchlistResponse): StockView[] =>
  d.items.filter((i) => i.kind === "stock").map(rowOf);
export const fundRows = (d: WatchlistResponse) =>
  d.items.filter((i) => i.kind === "fund").map((i) => ({ id: i.id, name: i.name ?? i.id }));
