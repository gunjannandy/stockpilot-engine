import { calendarReturns, sipReturn } from "@stockpilot/contract";
import { describe, expect, it } from "vitest";

// A fund growing 1% a month, one NAV on the first of each month, 4 years.
const steady = (): [string, number][] => {
  const out: [string, number][] = [];
  for (let i = 0; i < 48; i++) {
    const y = 2022 + Math.floor(i / 12);
    const m = (i % 12) + 1;
    out.push([`${y}-${String(m).padStart(2, "0")}-01`, Number((100 * 1.01 ** i).toFixed(4))]);
  }
  out.push(["2025-12-31", Number((100 * 1.01 ** 48).toFixed(4))]);
  return out;
};

describe("fund detail numbers from NAVs (C-075-1)", () => {
  it("calendar-year returns need the previous year end and flag a part year", () => {
    const r = calendarReturns([
      ["2023-12-29", 100],
      ["2024-12-31", 110],
      ["2025-06-30", 99],
    ]);
    expect(r).toEqual([
      { year: 2024, ret: 10, partial: false },
      { year: 2025, ret: -10, partial: true },
    ]);
    expect(calendarReturns([["2024-12-31", 110]])).toEqual([]);
  });

  it("a monthly SIP in a steadily growing fund returns about its growth rate", () => {
    const r = sipReturn(steady(), 36);
    expect(r).not.toBeNull();
    expect(Math.abs((r as number) - (1.01 ** 12 - 1) * 100)).toBeLessThan(1.5);
  });

  it("a SIP asked for more months than there is history gives null, never a number", () => {
    expect(sipReturn(steady().slice(0, 20), 36)).toBeNull();
    expect(sipReturn([], 36)).toBeNull();
  });
});
