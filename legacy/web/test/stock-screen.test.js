// T22: the stock screen. Pure parts (ranges, series, markers, forecast bands, fact groups, the nine-part form) are tested here;
// the drawing itself is checked with real screenshots (docs/status/shots-t22).
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const root = new URL("../../", import.meta.url);
const fixture = n => JSON.parse(readFileSync(new URL(`tests/fixtures/live/${n}.json`, root), "utf8"));
const ctx = { console };   // a bare context: no window, no document, so the file must load as plain functions
vm.runInNewContext(readFileSync(new URL("web/public/screens/stock.js", root), "utf8"), ctx);
const K = ctx.SPStock;

// one year of weekday candles ending on 2026-11-23, so every range has something to show
function longChart(n = 1500) {
  const dates = [], close = [];
  const d = new Date("2026-11-23T00:00:00Z");
  while (dates.length < n) { if (d.getUTCDay() % 6) { dates.unshift(d.toISOString().slice(0, 10)); close.unshift(100 + dates.length * 0 + (n - dates.length) * 0.05); } d.setUTCDate(d.getUTCDate() - 1); }
  const m = a => a.map(() => 1);
  return { symbol: "FIXA", dates, open: close, high: close.map(v => v + 1), low: close.map(v => v - 1), close, volume: close.map(() => 1000), dma50: dates.map((_, i) => (i < 49 ? null : 100)), dma200: dates.map((_, i) => (i < 199 ? null : 100)) };
}

describe("ranges", () => {
  const c = longChart();
  it("offers 1M, 6M, 1Y, 5Y and All", () => expect(K.RANGES).toEqual(["1M", "6M", "1Y", "5Y", "All"]));
  it("All starts at the first candle, back to listing", () => expect(K.rangeStart("All", c.dates)).toBe(c.dates[0]));
  it("1Y starts one calendar year before the last candle", () => expect(K.rangeStart("1Y", c.dates) >= "2025-11-23" && K.rangeStart("1Y", c.dates) <= "2025-11-27").toBe(true));
  it("1M and 6M start a month and six months back", () => {
    expect(K.rangeStart("1M", c.dates) >= "2026-10-20").toBe(true);
    expect(K.rangeStart("6M", c.dates) >= "2026-05-17").toBe(true);
  });
  it("a stock listed last week shows all it has for every range", () => {
    const young = fixture("files/chart_history");
    for (const r of K.RANGES) expect(K.rangeStart(r, young.dates)).toBe(young.dates[0]);
  });
});

describe("series", () => {
  const chart = fixture("files/chart_history");
  it("turns equal-length columns into candles, volume and two lines", () => {
    const s = K.seriesOf(chart);
    expect(s.candles).toHaveLength(chart.dates.length);
    expect(s.candles[0]).toEqual({ time: chart.dates[0], open: chart.open[0], high: chart.high[0], low: chart.low[0], close: chart.close[0] });
    expect(s.volume[0].time).toBe(chart.dates[0]);
    expect(s.volume.every(v => v.color)).toBe(true);
  });
  it("leaves out averages that are not there yet instead of drawing zero", () => {
    const s = K.seriesOf({ ...chart, dma50: [null, null, 5, 6, 7], dma200: [null, null, null, null, null] });
    expect(s.dma50.map(p => p.value)).toEqual([5, 6, 7]);
    expect(s.dma200).toEqual([]);
  });
  it("skips a day with no price and never throws on a short column", () => {
    const s = K.seriesOf({ ...chart, close: chart.close.slice(0, 3), open: chart.open, high: chart.high, low: chart.low });
    expect(s.candles.length).toBeLessThanOrEqual(3);
  });
  it("returns empty series for no chart at all", () => expect(K.seriesOf(null).candles).toEqual([]));
});

describe("markers for the father's buys and sells and our past calls", () => {
  const dates = ["2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20", "2026-11-23"];
  it("puts a buy as a green up arrow under the candle, a sell as a red down arrow over it", () => {
    const m = K.markersOf([{ date: "2026-11-18", kind: "buy", qty: 10 }, { date: "2026-11-20", kind: "sell", qty: 4 }], dates, "en");
    expect(m[0]).toMatchObject({ time: "2026-11-18", position: "belowBar", shape: "arrowUp" });
    expect(m[1]).toMatchObject({ time: "2026-11-20", position: "aboveBar", shape: "arrowDown" });
    expect(m[0].text).toMatch(/10/);
  });
  it("moves a weekend trade to the next trading day on screen", () => {
    const m = K.markersOf([{ date: "2026-11-21", kind: "buy", qty: 1 }], dates, "en");
    expect(m[0].time).toBe("2026-11-23");
  });
  it("drops a trade made before the first candle or after the last", () => {
    expect(K.markersOf([{ date: "2020-01-01", kind: "buy", qty: 1 }, { date: "2030-01-01", kind: "buy", qty: 1 }], dates, "en")).toEqual([]);
  });
  it("sorts by time (the chart library requires it) and keeps at most one marker per kind per day", () => {
    const m = K.markersOf([{ date: "2026-11-20", kind: "buy", qty: 1 }, { date: "2026-11-17", kind: "call", call: "buy" }, { date: "2026-11-20", kind: "buy", qty: 2 }], dates, "en");
    expect(m.map(x => x.time)).toEqual(["2026-11-17", "2026-11-20"]);
    expect(m[1].text).toMatch(/3/);   // the two buys that day are one dot with the total
  });
  it("names a past call in plain words, in Bengali too", () => {
    const en = K.markersOf([{ date: "2026-11-18", kind: "call", call: "sell" }], dates, "en")[0];
    const bn = K.markersOf([{ date: "2026-11-18", kind: "call", call: "sell" }], dates, "bn")[0];
    expect(en.shape).toBe("circle");
    expect(en.text).not.toEqual(bn.text);
    expect(/[ঀ-৿]/.test(bn.text)).toBe(true);
  });
});

describe("forecast bands drawn ahead of today", () => {
  const call = fixture("routes/call_get").response.call;
  const b = K.bandsOf(call, "2026-11-23", 103);
  it("starts at today's close with no width and widens", () => {
    expect(b.points[0]).toMatchObject({ time: "2026-11-23", lo80: 103, hi80: 103, lo50: 103, hi50: 103, mid: 103 });
    const widths = b.points.map(p => p.hi80 - p.lo80);
    for (let i = 1; i < widths.length; i++) expect(widths[i]).toBeGreaterThanOrEqual(widths[i - 1] - 1e-9);
  });
  it("hits the model's low, likely and high at 1, 3 and 6 months", () => {
    const at = (t, k) => b.nodes.find(n => n.key === t)[k];
    expect(at("1m", "lo80")).toBe(call.low_1m); expect(at("3m", "mid")).toBe(call.likely_3m); expect(at("6m", "hi80")).toBe(call.high_6m);
  });
  it("the darker 50% band sits inside the lighter 80% band, around the likely price", () => {
    for (const p of b.points) { expect(p.lo50).toBeGreaterThanOrEqual(p.lo80 - 1e-9); expect(p.hi50).toBeLessThanOrEqual(p.hi80 + 1e-9); expect(p.mid).toBeGreaterThanOrEqual(p.lo50 - 1e-9); expect(p.mid).toBeLessThanOrEqual(p.hi50 + 1e-9); }
  });
  it("ends six months ahead on a weekday", () => {
    const last = b.points[b.points.length - 1].time;
    expect(last >= "2027-05-15" && last <= "2027-05-30").toBe(true);
    expect(new Date(last + "T00:00:00Z").getUTCDay() % 6).not.toBe(0);
  });
  it("falls back to the form's bands, and to nothing when there is no forecast", () => {
    const only = { form: { bands: { "1m": [90, 100, 110], "3m": [85, 100, 120], "6m": [80, 100, 130] } } };
    expect(K.bandsOf(only, "2026-11-23", 100).nodes.find(n => n.key === "6m").hi80).toBe(130);
    expect(K.bandsOf(null, "2026-11-23", 100)).toBeNull();
    expect(K.bandsOf({ low_1m: null }, "2026-11-23", 100)).toBeNull();
  });
  it("a range that is not ordered is not drawn (the code checks reject it, the screen never invents one)", () => {
    expect(K.bandsOf({ ...call, low_3m: 200 }, "2026-11-23", 103)).toBeNull();
  });
});

describe("facts in four groups, each number with one plain sentence", () => {
  const facts = fixture("files/stock_facts");
  const g = K.factGroups(facts, "en");
  it("has price, value, quality and events, in that order", () => expect(g.map(x => x.key)).toEqual(["price", "value", "quality", "events"]));
  it("gives every shown number its sentence, or a plain not-available line", () => {
    for (const grp of g) for (const r of grp.rows) { expect(r.label).toBeTruthy(); expect(r.value).toBeTruthy(); expect(typeof r.sentence).toBe("string"); }
  });
  it("uses the file's sentence when it has one and in Bengali when asked", () => {
    const pe = g.find(x => x.key === "value").rows.find(r => r.key === "pe");
    expect(pe.sentence).toBe("Cheaper than its sector.");
    const bn = K.factGroups(facts, "bn").find(x => x.key === "value").rows.find(r => r.key === "pe");
    expect(bn.sentence).toBe("সেক্টরের চেয়ে সস্তা।");
  });
  it("shows an English sentence with the EN flag when Bengali is missing, never a blank", () => {
    const noBn = { ...facts, sentences: [{ key: "pe", en: "Cheaper than its sector.", bn: null }] };
    const pe = K.factGroups(noBn, "bn").find(x => x.key === "value").rows.find(r => r.key === "pe");
    expect(pe.sentence).toBe("Cheaper than its sector.");
    expect(pe.en).toBe(true);
  });
  it("a number the file does not have reads as not available, not as zero", () => {
    const row = g.find(x => x.key === "price").rows.find(r => r.key === "delivery");
    expect(row.value).toMatch(/not available/i);
  });
  it("the same rows exist before the file loads (no layout shift)", () => {
    expect(K.factGroups(null, "en").map(x => x.rows.length)).toEqual(g.map(x => x.rows.length));
  });
  it("lists events with the date, soonest first", () => {
    const ev = g.find(x => x.key === "events").rows;
    expect(ev[0].value).toMatch(/10 Dec/);
  });
  it("money is in rupees and growth keeps its sign", () => {
    const val = g.find(x => x.key === "value").rows.find(r => r.key === "mcap");
    expect(val.value).toMatch(/₹5,200 crore/);
    expect(g.find(x => x.key === "quality").rows.find(r => r.key === "profit").value).toMatch(/\+15\.5%/);
  });
});

describe("the nine-part form", () => {
  const call = fixture("routes/call_get").response.call;
  const v = K.formView(call, "en");
  it("reads the call, chances and confidence in plain words", () => {
    expect(v.call).toBe("buy"); expect(v.chance6).toBe(66); expect(v.chance3).toBe(62); expect(v.confidence).toBe("medium");
  });
  it("keeps the written parts in order, even when some are empty (nine parts: call, range, the seven below, Bengali by language)", () => {
    expect(v.parts.map(p => p.key)).toEqual(["history", "market", "news", "for", "against", "change", "risks"]);
  });
  it("lists reasons for and against with their weight", () => {
    const f = v.parts.find(p => p.key === "for").items[0];
    expect(f.text).toBe("Profit is growing"); expect(f.weight).toBe(3);
  });
  it("shows a level the view hinges on as a number and a sentence", () => {
    expect(v.parts.find(p => p.key === "change").items[0]).toMatchObject({ level: 95 });
  });
  it("is out of date when the row says so, and shows the amber chip", () => {
    expect(K.formView({ ...call, out_of_date: true }, "en").stale).toBe(true);
    expect(K.formView(call, "en").stale).toBe(false);
  });
  it("is null for a stock we never forecast (the page offers Analyse instead)", () => expect(K.formView(null, "en")).toBeNull());
  it("tells a code-route call from a news-route call", () => {
    expect(v.route).toBe("code"); expect(K.formView({ ...call, route: "news", news_buy: true }, "en").newsBuy).toBe(true);
  });
  it("uses Bengali sentences from the form when present", () => {
    expect(K.formView(call, "bn").bengaliSummary).toBe("ভালো কোম্পানি, এখন কেনা যায়");
  });
});

describe("the screen's own words", () => {
  it("every English word has Bengali, and every English sentence has Bengali letters", () => {
    const { en, bn } = K.words;
    expect(Object.keys(en).filter(k => !(k in bn))).toEqual([]);
    const bad = Object.entries(en).filter(([k, v]) => typeof v === "string" && v.split(/\s+/).length >= 3 && !/[ঀ-৿]/.test(bn[k] || "")).map(([k]) => k);
    expect(bad).toEqual([]);
  });
});

describe("the page frame", () => {
  it("reserves the chart's height from the first paint and carries the symbol", () => {
    const h = K.html({ symbol: "FIXA", name: "Fixture Alpha Ltd", lang: "en", exchange: "NSE" });
    expect(h).toMatch(/data-sk-chart="FIXA"/);
    expect(h).toMatch(/class="sk-cv"/);
    expect(h).toMatch(/Fixture Alpha Ltd/);
  });
  it("escapes names", () => expect(K.html({ symbol: "X", name: "<img onerror=1>", lang: "en" })).not.toMatch(/<img onerror/));
  it("always offers Analyse, so any stock can be forecast", () => expect(K.html({ symbol: "ZZZ", name: "Z", lang: "en" })).toMatch(/data-sk-analyse/));
});
