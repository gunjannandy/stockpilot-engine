import { describe, expect, it } from "vitest";
import { bandsOf, monthLabel, rangeStart, sma, wheelZoom } from "./series";

const dates = ["2021-11-26", "2025-11-27", "2026-05-27", "2026-11-26", "2026-11-27"];
describe("chart maths", () => {
  it("averages over the window", () => {
    const bars = [1, 2, 3, 4].map((c, i) => ({ time: `2026-01-0${i + 1}`, close: c }));
    expect(sma(bars, 2).map((p) => p.value)).toEqual([1.5, 2.5, 3.5]);
  });
  it("plain scroll never zooms; Ctrl or Cmd scroll does", () => {
    expect(wheelZoom({ ctrlKey: false, metaKey: false, deltaY: -100 })).toBeNull();
    expect(wheelZoom({ ctrlKey: true, metaKey: false, deltaY: -100 })).toBeLessThan(1);
    expect(wheelZoom({ ctrlKey: false, metaKey: true, deltaY: 100 })).toBeGreaterThan(1);
  });
  it("starts every range at the right day, never before listing", () => {
    expect(rangeStart("1Y", dates)).toBe("2025-11-27");
    expect(rangeStart("6M", dates)).toBe("2026-05-27");
    expect(rangeStart("1M", dates)).toBe("2026-11-26");
    expect(rangeStart("5D", dates)).toBe("2021-11-26");
    expect(rangeStart("1W", dates)).toBe("2026-11-26");
    expect(rangeStart("All", dates)).toBe("2021-11-26");
    expect(rangeStart("5Y", dates)).toBe("2025-11-27"); // first date on or after 5 years back
  });
  it("widens the band with time and rejects a broken one", () => {
    const call = { low: [90, 80, 70], likely: [100, 100, 100], high: [110, 120, 130] } as never;
    const b = bandsOf(call, "2026-11-27", 100);
    const w = (i: number) => (b?.points[i]?.hi80 ?? 0) - (b?.points[i]?.lo80 ?? 0);
    expect(w(60)).toBeGreaterThan(w(5));
    expect(
      bandsOf(
        { low: [120, 80, 70], likely: [100, 100, 100], high: [110, 120, 130] },
        "2026-11-27",
        100,
      ),
    ).toBeNull();
  });
  it("labels months like v2", () => {
    expect(monthLabel("2025-12-03")).toBe("Dec ’25");
    expect(monthLabel("2026-01-02")).toBe("2026");
  });
});
