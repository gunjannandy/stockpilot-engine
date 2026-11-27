// C-118-1: the freshness rule across holidays and IST display.
import { expect, it } from "vitest";
import { istText } from "../api/src/app";
import { type Calendar, expectedAsOf, isFresh } from "../api/src/calendar/calendar";

const cal: Calendar = {
  rows: [{ id: "h", kind: "holiday", date: "2026-11-30", reason: "Holiday" }],
};
// Times are UTC instants; 03:00Z is 08:30 IST.
const at = (iso: string) => new Date(iso);

it("C-118-1 the last trading day's close is due by 08:30 IST the next morning", () => {
  // Thu 26 Nov 08:29 IST: Wednesday's close is not yet due, Tuesday's is the last one.
  expect(expectedAsOf(cal, at("2026-11-26T02:59:00Z"))).toBe("2026-11-24");
  // Thu 26 Nov 08:30 IST: Wednesday's close is due now.
  expect(expectedAsOf(cal, at("2026-11-26T03:00:00Z"))).toBe("2026-11-25");
  // Fri 27 Nov 08:30 IST: Thursday's close is due now.
  expect(expectedAsOf(cal, at("2026-11-27T03:00:00Z"))).toBe("2026-11-26");
});

it("C-118-1 across a weekend and a holiday the last trading day stays due", () => {
  // Mon 30 Nov is a holiday: Friday's close (due Sat 08:30) stays the one due through Tuesday morning.
  expect(expectedAsOf(cal, at("2026-11-30T09:00:00Z"))).toBe("2026-11-27");
  expect(expectedAsOf(cal, at("2026-12-01T03:00:00Z"))).toBe("2026-11-27");
  // Tue 1 Dec 15:30 IST closes; due Wed 2 Dec 08:30 IST.
  expect(expectedAsOf(cal, at("2026-12-02T03:00:00Z"))).toBe("2026-12-01");
});

it("C-118-1 data is fresh when its as-of date reaches the due close", () => {
  const now = at("2026-12-01T05:00:00Z");
  expect(isFresh(cal, "2026-11-27", now)).toBe(true);
  expect(isFresh(cal, "2026-11-26", now)).toBe(false);
  expect(isFresh(cal, "2026-12-01", now)).toBe(true);
});

it("C-118-1 stored in UTC, shown in IST", () => {
  expect(istText(at("2026-11-27T03:00:00Z"))).toBe("2026-11-27T08:30:00+05:30");
  // Late evening UTC is already the next IST day.
  expect(istText(at("2026-11-27T20:00:00Z"))).toBe("2026-11-28T01:30:00+05:30");
});
