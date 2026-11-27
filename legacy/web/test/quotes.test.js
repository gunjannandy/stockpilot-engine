// T15: near-live prices for stocks in the news. Yahoo first, NSE as a bonus, spaced calls, age always kept.
import { beforeEach, describe, expect, it } from "vitest";
import { localD1 } from "./d1.js";
import { marketOpen, parseYahoo, parseNse, newsSymbols, refreshQuotes, MAX_SYMBOLS, SPACING_MS } from "../lib/v2/quotes.js";

const OPEN = new Date("2026-11-25T10:00:00+05:30");   // a Wednesday
const yahoo = (price, tSec, prev = 100) => ({ chart: { result: [{ meta: { symbol: "X.NS", regularMarketPrice: price, chartPreviousClose: prev, regularMarketTime: tSec } }] } });
const ok = (b) => ({ ok: true, status: 200, json: async () => b, headers: { getSetCookie: () => ["nsit=abc; Path=/"] } });
const bad = (s = 429) => ({ ok: false, status: s, json: async () => ({}), headers: { getSetCookie: () => [] } });
let db;
beforeEach(() => { db = localD1(); });

describe("market hours", () => {
  it("is open 09:15 to 15:30 IST on weekdays only", () => {
    expect(marketOpen(new Date("2026-11-25T09:14:00+05:30"))).toBe(false);
    expect(marketOpen(new Date("2026-11-25T09:15:00+05:30"))).toBe(true);
    expect(marketOpen(new Date("2026-11-25T15:30:00+05:30"))).toBe(true);
    expect(marketOpen(new Date("2026-11-25T15:31:00+05:30"))).toBe(false);
    expect(marketOpen(new Date("2026-11-28T11:00:00+05:30"))).toBe(false);   // Saturday
  });
});

describe("parsers", () => {
  it("reads a Yahoo chart answer into price, previous close and an IST time", () => {
    const r = parseYahoo(yahoo(104.5, Date.parse("2026-11-25T09:59:00+05:30") / 1000, 101));
    expect(r).toEqual({ price: 104.5, prev_close: 101, as_of: "2026-11-25T09:59:00+05:30" });
    expect(parseYahoo({})).toBeNull();
    expect(parseYahoo(yahoo("n/a", 1))).toBeNull();
  });
  it("reads an NSE quote and its 'dd-Mon-yyyy hh:mm:ss' time", () => {
    expect(parseNse({ priceInfo: { lastPrice: 55.2, previousClose: 54, lastUpdateTime: "25-Nov-2026 10:01:05" } }, OPEN))
      .toEqual({ price: 55.2, prev_close: 54, as_of: "2026-11-25T10:01:05+05:30" });
    expect(parseNse({ priceInfo: { lastPrice: 55.2, previousClose: 54, lastUpdateTime: "garbage" } }, OPEN).as_of).toBe("2026-11-25T10:00:00+05:30");
    expect(parseNse({}, OPEN)).toBeNull();
  });
});

describe("which stocks are in the news", () => {
  it("takes the symbols tagged on recent news, newest first, once each, capped", async () => {
    const s = await newsSymbols(db, OPEN);
    expect(s.length).toBeGreaterThan(0);
    expect(new Set(s.map((x) => x.symbol + x.exchange)).size).toBe(s.length);
    expect(s.length).toBeLessThanOrEqual(MAX_SYMBOLS);
  });
  it("ignores news older than two days", async () => {
    expect(await newsSymbols(db, new Date("2026-12-30T10:00:00+05:30"))).toEqual([]);
  });
});

describe("refreshQuotes", () => {
  const syms = [{ symbol: "AAA", exchange: "NSE" }, { symbol: "BBB", exchange: "NSE" }, { symbol: "CCC", exchange: "BSE" }];
  const run = (fetch, extra = {}) => { const waits = []; return refreshQuotes({ db, symbols: syms, fetch, now: OPEN, sleep: async (ms) => { waits.push(ms); }, ...extra }).then((r) => ({ ...r, waits })); };
  const fresh = Math.floor(OPEN.getTime() / 1000) - 60;

  it("writes Yahoo prices with source and time, using .NS and .BO", async () => {
    const urls = [];
    const r = await run(async (u) => { urls.push(u); return ok(yahoo(200, fresh)); });
    expect(r.written).toBe(3);
    expect(urls.some((u) => u.includes("AAA.NS")) && urls.some((u) => u.includes("CCC.BO"))).toBe(true);
    const row = db.db.prepare("select * from quotes where symbol='AAA'").get();
    expect(row).toMatchObject({ exchange: "NSE", price: 200, source: "yahoo", as_of: "2026-11-25T09:59:00+05:30" });
  });

  it("spaces its calls so the sources are never hammered", async () => {
    const r = await run(async () => ok(yahoo(200, fresh)));
    expect(SPACING_MS).toBeGreaterThanOrEqual(250);
    expect(r.waits.length).toBe(syms.length - 1);
    expect(r.waits.every((w) => w >= SPACING_MS)).toBe(true);
  });

  it("falls back to NSE for an NSE stock when Yahoo refuses, and records source nse", async () => {
    const r = await run(async (u) => {
      if (u.includes("yahoo")) return bad();
      if (u.includes("quote-equity")) return ok({ priceInfo: { lastPrice: 77, previousClose: 70, lastUpdateTime: "25-Nov-2026 09:58:00" } });
      return ok({});
    });
    const rows = db.db.prepare("select symbol, source, price from quotes where symbol in ('AAA','BBB')").all();
    expect(rows.map((x) => x.source)).toEqual(["nse", "nse"]);
    expect(r.failed).toEqual(["CCC"]);   // BSE has no NSE fallback
  });

  it("takes NSE's price when Yahoo's is older than 15 minutes", async () => {
    const old = Math.floor(OPEN.getTime() / 1000) - 3600;
    await run(async (u) => u.includes("yahoo") ? ok(yahoo(10, old)) : u.includes("quote-equity") ? ok({ priceInfo: { lastPrice: 11, previousClose: 9, lastUpdateTime: "25-Nov-2026 09:59:30" } }) : ok({}), { symbols: [syms[0]] });
    expect(db.db.prepare("select source, price from quotes where symbol='AAA'").get()).toEqual({ source: "nse", price: 11 });
  });

  it("stays inside the free Worker's 50 subrequests, even when everything falls back", async () => {
    const many = Array.from({ length: MAX_SYMBOLS + 10 }, (_, i) => ({ symbol: "S" + i, exchange: "NSE" }));
    let n = 0;
    await refreshQuotes({ db, symbols: many, fetch: async () => { n++; return bad(); }, now: OPEN, sleep: async () => {} });
    expect(n).toBeLessThanOrEqual(40);
  });

  it("never replaces a newer stored price with an older one", async () => {
    await run(async () => ok(yahoo(200, fresh)));
    await run(async () => ok(yahoo(150, fresh - 600)));
    expect(db.db.prepare("select price from quotes where symbol='AAA'").get().price).toBe(200);
  });

  it("counts its writes in today's budget and stops when the budget is reached", async () => {
    await run(async () => ok(yahoo(200, fresh)));
    expect(db.db.prepare("select writes from write_budget where day='2026-11-25'").get().writes).toBeGreaterThanOrEqual(3);
    db.db.prepare("update write_budget set writes = 85000 where day='2026-11-25'").run();
    let n = 0;
    const r = await run(async () => { n++; return ok(yahoo(1, fresh)); });
    expect(n).toBe(0); expect(r.stopped).toBe(true);
  });

  it("skips a symbol refreshed less than minAgeSeconds ago", async () => {
    await run(async () => ok(yahoo(200, fresh)));
    let n = 0;
    await run(async () => { n++; return ok(yahoo(201, fresh + 30)); }, { minAgeSeconds: 600 });
    expect(n).toBe(0);
  });

  it("survives a network error on one symbol", async () => {
    let i = 0;
    const r = await run(async () => { if (i++ === 0) throw new Error("boom"); return ok(yahoo(5, fresh)); });
    expect(r.written).toBe(2);
  });
});
