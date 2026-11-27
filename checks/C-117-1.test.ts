// C-117-1: calendar and corporate-action adjustments from fixtures.
import { expect, it } from "vitest";
import {
  adjustedPrice,
  adjustmentFactor,
  type Calendar,
  currentSymbol,
  isDelisted,
  isTradingDay,
  lastTradingDay,
  nextTradingDay,
} from "../api/src/calendar/calendar";

const cal: Calendar = {
  rows: [
    { id: "h1", kind: "holiday", date: "2026-11-30", reason: "Guru Nanak Jayanti" },
    { id: "s1", kind: "special", date: "2026-11-28", reason: "Special live session" },
    { id: "a1", kind: "split", date: "2026-06-10", symbol: "ABC", old_shares: 1, new_shares: 5 },
    { id: "a2", kind: "bonus", date: "2026-09-01", symbol: "ABC", old_shares: 1, new_shares: 1 },
    { id: "a3", kind: "symbol_change", date: "2026-10-01", symbol: "OLDCO", new_symbol: "NEWCO" },
    { id: "a4", kind: "delisting", date: "2026-11-20", symbol: "GONE" },
  ],
};

it("C-117-1 weekends and holidays are closed, a special session on a weekend is open", () => {
  expect(isTradingDay(cal, "2026-11-27")).toEqual({ is_trading_day: true, reason: null });
  expect(isTradingDay(cal, "2026-11-29")).toEqual({ is_trading_day: false, reason: "Weekend" });
  expect(isTradingDay(cal, "2026-11-30")).toEqual({
    is_trading_day: false,
    reason: "Guru Nanak Jayanti",
  });
  expect(isTradingDay(cal, "2026-11-28")).toEqual({ is_trading_day: true, reason: null });
});

it("C-117-1 last and next trading day skip closed days", () => {
  expect(lastTradingDay(cal, "2026-11-30")).toBe("2026-11-28");
  expect(lastTradingDay(cal, "2026-11-27")).toBe("2026-11-27");
  expect(nextTradingDay(cal, "2026-11-28")).toBe("2026-12-01");
});

it("C-117-1 a split and a bonus scale the prices before their ex-dates", () => {
  // 1:5 split on 10 Jun, then 1:1 bonus on 1 Sep: a price before both is divided by 5 and by 2.
  expect(adjustmentFactor(cal, "ABC", "2026-01-15")).toBeCloseTo(1 / 10, 12);
  expect(adjustmentFactor(cal, "ABC", "2026-07-01")).toBeCloseTo(1 / 2, 12);
  expect(adjustmentFactor(cal, "ABC", "2026-09-01")).toBe(1);
  expect(adjustedPrice(cal, "ABC", 1000, "2026-01-15")).toBe(100);
  expect(adjustmentFactor(cal, "OTHER", "2026-01-15")).toBe(1);
});

it("C-117-1 symbol changes resolve to today's name and delistings end a symbol", () => {
  expect(currentSymbol(cal, "OLDCO")).toBe("NEWCO");
  expect(currentSymbol(cal, "NEWCO")).toBe("NEWCO");
  expect(currentSymbol(cal, "ABC")).toBe("ABC");
  expect(isDelisted(cal, "GONE", "2026-11-19")).toBe(false);
  expect(isDelisted(cal, "GONE", "2026-11-20")).toBe(true);
});
