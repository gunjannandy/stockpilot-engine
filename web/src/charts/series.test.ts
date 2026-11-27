import { describe, expect, it } from "vitest";
import { band, rangeStart, sma, wheelZoom } from "./series";

describe("chart maths", () => {
  it("averages over the window", () => {
    const bars = [1, 2, 3, 4].map((c, i) => ({ time: `2026-01-0${i + 1}`, close: c }));
    expect(sma(bars, 2).map((p) => p.value)).toEqual([1.5, 2.5, 3.5]);
  });
  it("plain scroll never zooms; Ctrl or Cmd scroll does", () => {
    expect(wheelZoom({ ctrlKey: false, metaKey: false, deltaY: -100 })).toBeNull();
    expect(wheelZoom({ ctrlKey: true, metaKey: false, deltaY: -100 })).toBeGreaterThan(1);
    expect(wheelZoom({ ctrlKey: false, metaKey: true, deltaY: 100 })).toBeLessThan(1);
  });
  it("starts ranges at the right day and never before listing", () => {
    expect(rangeStart("2026-11-27", "1y", "2000-01-01")).toBe("2025-11-27");
    expect(rangeStart("2026-11-27", "6m", "2026-10-01")).toBe("2026-10-01");
    expect(rangeStart("2026-11-27", "all", "2010-05-05")).toBe("2010-05-05");
  });
  it("widens the band with time", () => {
    const b = band(100, 20, 0.01, 10);
    const w = (i: number) => (b[i]?.hi ?? 0) - (b[i]?.lo ?? 0);
    expect(w(1)).toBeGreaterThan(w(0));
  });
});
