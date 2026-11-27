// T26: the fund screen's rules. Neutral invented data only.
import { describe, it, expect } from "vitest";
await import("../public/screens/funds-core.js");
const F = globalThis.SPFundsCore;

const DAY = 86400000;
// A fund that rises 12% a year, evenly, from 2006-01-02, one NAV a day (weekdays only are fine).
function steady(from = "2006-01-02", years = 20, rate = 0.12, start = 10) {
  const dates = [], nav = [], t0 = Date.parse(from);
  for (let d = 0; d < years * 365; d++) { const t = t0 + d * DAY; dates.push(new Date(t).toISOString().slice(0, 10)); nav.push(start * Math.pow(1 + rate, d / 365)); }
  return { dates, nav };
}

describe("returns", () => {
  const s = steady();
  it("yearly rate over 1, 3 and 5 years matches the rate built in", () => {
    for (const y of [1, 3, 5]) expect(F.cagr(s, y)).toBeCloseTo(12, 0);
  });
  it("is null when the fund is younger than the window", () => {
    const young = steady("2025-01-01", 1.5);
    expect(F.cagr(young, 3)).toBeNull();
    expect(F.cagr({ dates: [], nav: [] }, 1)).toBeNull();
  });
  it("rolling returns come monthly with min, middle and max", () => {
    const r = F.rolling(s, 3), st = F.rollStats(r);
    expect(r.length).toBeGreaterThan(100);
    expect(st.min).toBeCloseTo(12, 0); expect(st.max).toBeCloseTo(12, 0); expect(st.positive).toBe(1);
  });
});

describe("falls in bad markets", () => {
  it("measures the peak-to-trough fall inside each named market, and skips markets before the fund existed", () => {
    const dates = ["2020-01-17", "2020-02-14", "2020-03-23", "2020-06-01"], nav = [100, 105, 70, 90];
    const out = F.falls({ dates, nav }, null);
    const covid = out.find(f => f.id === "covid");
    expect(covid.fund).toBeCloseTo(-33.3, 0);
    expect(out.find(f => f.id === "gfc")).toBeUndefined();
  });
  it("sets the benchmark's fall beside the fund's, when given", () => {
    const fund = { dates: ["2020-01-17", "2020-03-23"], nav: [100, 80] }, bench = { dates: ["2020-01-17", "2020-03-23"], nav: [100, 60] };
    const c = F.falls(fund, bench).find(f => f.id === "covid");
    expect(c.fund).toBeCloseTo(-20, 0); expect(c.bench).toBeCloseTo(-40, 0);
  });
  it("worst fall since launch", () => {
    expect(F.worstFall({ dates: ["a", "b", "c", "d"], nav: [10, 20, 12, 30] })).toBeCloseTo(-40, 5);
  });
});

describe("consistency", () => {
  it("is the share of rolling-year windows the fund beat the other series", () => {
    const fund = steady("2010-01-01", 10, 0.12), other = steady("2010-01-01", 10, 0.10);
    expect(F.beatShare(fund, other, 1)).toBe(1);
    expect(F.beatShare(other, fund, 1)).toBe(0);
    expect(F.beatShare(fund, null, 1)).toBeNull();
  });
  it("against a category median line given as months and values", () => {
    const fund = steady("2010-01-01", 10, 0.12);
    const months = F.rolling(fund, 1).map(r => r.date);
    const cat = { months, med1y: months.map(() => 20) };
    expect(F.beatCategory(fund, cat)).toBe(0);
    expect(F.beatCategory(fund, { months, med1y: months.map(() => 1) })).toBe(1);
    expect(F.beatCategory(fund, null)).toBeNull();
  });
});

describe("chart ranges and buys", () => {
  it("cuts the series by range, All keeps everything", () => {
    const s = steady("2010-01-01", 10);
    expect(F.slice(s, "All").dates.length).toBe(s.dates.length);
    const y1 = F.slice(s, "1Y"); expect(y1.dates.length).toBeGreaterThan(360); expect(y1.dates.length).toBeLessThan(370);
    expect(F.slice(s, "5Y").dates.length).toBeGreaterThan(1800);
  });
  it("puts each buy on the chart at the NAV of the day, skipping buys outside the history", () => {
    const s = { dates: ["2024-01-01", "2024-01-02", "2024-01-05"], nav: [10, 11, 12] };
    const dots = F.buyDots(s, [{ acquired_on: "2024-01-03", quantity: 5, cost: 11.5 }, { acquired_on: "2020-01-01", quantity: 1, cost: 5 }]);
    expect(dots).toEqual([{ i: 1, date: "2024-01-03", quantity: 5, cost: 11.5 }]);
  });
});

describe("overlap with held stocks", () => {
  const rows = [{ isin: "INE000A00001", name: "Alpha Ltd", pct_nav: 6.5 }, { isin: "INE000B00002", name: "Beta Ltd", pct_nav: 3 }, { isin: "INE000C00003", name: "Gamma Ltd", pct_nav: 1 }, { isin: "INF000D00004", name: "Some Fund", pct_nav: 2 }];
  it("lists shared stocks and their weight, same as the Python function", () => {
    const o = F.overlap(rows, new Set(["INE000A00001", "INE000C00003", "INE999Z00009"]));
    expect(o.n_shared).toBe(2); expect(o.pct_nav).toBe(7.5); expect(o.shared.map(s => s.name)).toEqual(["Alpha Ltd", "Gamma Ltd"]);
    expect(o.pct_of_fund_stocks).toBeCloseTo(66.7, 1);
  });
  it("nothing held means no overlap, and no holdings file means null", () => {
    expect(F.overlap(rows, new Set()).n_shared).toBe(0);
    expect(F.overlap(null, new Set(["x"]))).toBeNull();
  });
});

describe("find a fund", () => {
  const entries = [
    { id: "a", name: "Alpha Bluechip Fund", amc: "Alpha Mutual Fund", group: "Equity", aliases: [] },
    { id: "b", name: "Beta Small Cap Fund", amc: "Beta Mutual Fund", group: "Equity", aliases: [] },
    { id: "c", name: "Gamma Liquid Fund", amc: "Gamma Mutual Fund", group: "Debt", aliases: [] },
  ];
  it("forgives spelling and filters by kind", async () => {
    await import("../public/search.js");
    const Fuse = (await import("fuse.js")).default;
    const f = F.finder(Fuse, entries);
    expect(f.find("bluchip").map(e => e.id)).toEqual(["a"]);
    expect(f.find("fund", { group: "Debt" }).map(e => e.id)).toEqual(["c"]);
    expect(f.find("", { group: "Equity" }).length).toBe(2);
  });
});

describe("plain words for a figure", () => {
  it("says how a fund did against its kind", () => {
    expect(F.vs(14, 11)).toBe("ahead");
    expect(F.vs(9, 11)).toBe("behind");
    expect(F.vs(11.2, 11)).toBe("level");
    expect(F.vs(null, 11)).toBeNull();
  });
});
