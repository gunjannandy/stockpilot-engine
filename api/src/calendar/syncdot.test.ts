import { describe, expect, it } from "vitest";
import type { Calendar } from "./calendar";
import { syncDot } from "./syncdot";

// 2026-11-26 is a Thursday, 27 Friday, 28 Saturday, 30 Monday. IST = UTC + 5:30.
const cal: Calendar = {
  rows: [{ id: "h1", kind: "holiday", date: "2026-11-30", reason: "Test holiday" }] as never,
};
const at = (ist: string) => new Date(`${ist}+05:30`);

describe("syncDot", () => {
  it("shows on a trading day when the last sync was before 09:15", () => {
    expect(syncDot(cal, "2026-11-26T18:00:00+05:30", at("2026-11-27T10:00:00"))).toBe(true);
    expect(syncDot(cal, "2026-11-27T09:14:00+05:30", at("2026-11-27T10:00:00"))).toBe(true);
  });
  it("clears at 09:15 sharp or any later sync that day", () => {
    expect(syncDot(cal, "2026-11-27T09:15:00+05:30", at("2026-11-27T10:00:00"))).toBe(false);
    expect(syncDot(cal, "2026-11-27T14:00:00+05:30", at("2026-11-27T15:00:00"))).toBe(false);
  });
  it("shows when there has never been a sync", () => {
    expect(syncDot(cal, null, at("2026-11-27T10:00:00"))).toBe(true);
  });
  it("never on a weekend", () => {
    expect(syncDot(cal, "2026-11-20T10:00:00+05:30", at("2026-11-28T10:00:00"))).toBe(false);
    expect(syncDot(cal, null, at("2026-11-29T10:00:00"))).toBe(false);
  });
  it("never on a market holiday", () => {
    expect(syncDot(cal, "2026-11-27T18:00:00+05:30", at("2026-11-30T10:00:00"))).toBe(false);
  });
  it("uses the IST day, not the UTC day", () => {
    // Friday 00:30 IST is still Thursday in UTC; the dot follows IST.
    expect(syncDot(cal, "2026-11-26T18:00:00+05:30", at("2026-11-27T00:30:00"))).toBe(true);
    // Saturday 01:00 IST is Friday in UTC but a weekend in IST.
    expect(syncDot(cal, null, at("2026-11-28T01:00:00"))).toBe(false);
  });
});
