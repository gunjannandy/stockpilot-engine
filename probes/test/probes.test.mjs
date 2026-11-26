import { describe, it, expect, beforeAll, afterAll } from "vitest";
import path from "node:path";
import { Miniflare } from "miniflare";
import { corsVerdict } from "../src/cors.mjs";
import { parseYahooChart, parseNseQuote } from "../src/quotes.mjs";
import { SCHEMA, nightStatements, D1_FREE_WRITES_PER_DAY } from "../src/night.mjs";

describe("og:image reader (runs inside workerd, where HTMLRewriter lives)", () => {
  const html = (head) => `<!doctype html><html><head>${head}</head><body>x</body></html>`;
  let mf;
  beforeAll(() => { mf = new Miniflare({ modules: true, modulesRoot: path.resolve("src"), scriptPath: path.resolve("src/og-worker.mjs"), script: undefined }); });
  afterAll(() => mf.dispose());
  const og = async (body, base) => {
    const r = await mf.dispatchFetch("http://t/?base=" + encodeURIComponent(base ?? ""), { method: "POST", body });
    return (await r.json()).image;
  };
  it("returns the og:image address", async () => {
    expect(await og(html('<meta property="og:image" content="https://cdn.example/a.jpg">'))).toBe("https://cdn.example/a.jpg");
  });
  it("accepts name= as well as property= and ignores other meta", async () => {
    expect(await og(html('<meta name="description" content="d"><meta name="og:image" content="https://cdn.example/b.png">'))).toBe("https://cdn.example/b.png");
  });
  it("returns null when there is none", async () => {
    expect(await og(html("<title>t</title>"))).toBeNull();
  });
  it("refuses non-http(s) addresses", async () => {
    expect(await og(html('<meta property="og:image" content="javascript:alert(1)">'))).toBeNull();
  });
  it("resolves a relative address against the page url", async () => {
    expect(await og(html('<meta property="og:image" content="/img/c.jpg">'), "https://news.example/story/1")).toBe("https://news.example/img/c.jpg");
  });
});

describe("cors verdict", () => {
  const origin = "https://stockpilotgn.pages.dev";
  it("passes with a matching allow-origin", () => {
    expect(corsVerdict({ "access-control-allow-origin": origin }, origin).ok).toBe(true);
  });
  it("passes with *", () => {
    expect(corsVerdict({ "access-control-allow-origin": "*" }, origin).ok).toBe(true);
  });
  it("fails with no header, saying why", () => {
    const v = corsVerdict({ "accept-ranges": "bytes" }, origin);
    expect(v.ok).toBe(false);
    expect(v.reason).toMatch(/no access-control-allow-origin/i);
  });
  it("fails for another origin", () => {
    expect(corsVerdict({ "access-control-allow-origin": "https://x.example" }, origin).ok).toBe(false);
  });
});

describe("quote parsers", () => {
  it("reads a Yahoo chart reply with age", () => {
    const j = { chart: { result: [{ meta: { regularMarketPrice: 101.5, regularMarketTime: 1000, symbol: "TCS.NS", chartPreviousClose: 100 } }] } };
    expect(parseYahooChart(j, 1300)).toEqual({ symbol: "TCS.NS", price: 101.5, prevClose: 100, asOf: 1000, ageSeconds: 300 });
  });
  it("returns null for a Yahoo error body", () => {
    expect(parseYahooChart({ chart: { result: null, error: { code: "Not Found" } } }, 1)).toBeNull();
  });
  it("reads an NSE quote reply", () => {
    const j = { info: { symbol: "TCS" }, priceInfo: { lastPrice: 55.25, previousClose: 54, lastUpdateTime: "25-Nov-2026 10:15:00" } };
    expect(parseNseQuote(j)).toEqual({ symbol: "TCS", price: 55.25, prevClose: 54, asOfText: "25-Nov-2026 10:15:00" });
  });
  it("returns null for an NSE reply with no price", () => {
    expect(parseNseQuote({})).toBeNull();
  });
});

describe("D1 night simulation", () => {
  it("writes one simulated night and reports rows written against the free budget", async () => {
    const mf = new Miniflare({ modules: true, script: "export default { fetch(){ return new Response('ok') } }", d1Databases: ["DB"] });
    const db = await mf.getD1Database("DB");
    for (const s of SCHEMA) await db.prepare(s).run();
    const night = nightStatements({ stocks: 2500, newsItems: 600, forecasts: 120 });
    let rows = 0;
    for (let i = 0; i < night.length; i += 50) {
      const res = await db.batch(night.slice(i, i + 50).map((s) => db.prepare(s.sql).bind(...s.args)));
      for (const r of res) rows += r.meta.rows_written;
    }
    await mf.dispose();
    expect(rows).toBeGreaterThan(0);
    expect(rows).toBeLessThan(D1_FREE_WRITES_PER_DAY);
  }, 60000);
});
