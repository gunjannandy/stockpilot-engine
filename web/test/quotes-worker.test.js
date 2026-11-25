// T15: the quote Worker's timer. Runs only in market hours, only for stocks in the news.
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { localD1 } from "./d1.js";
import worker from "../quotes/worker.js";

const yahoo = (t) => async () => ({ ok: true, status: 200, json: async () => ({ chart: { result: [{ meta: { regularMarketPrice: 9, chartPreviousClose: 8, regularMarketTime: t } }] } }), headers: { getSetCookie: () => [] } });
const at = (iso) => new Date(iso);

describe("quote Worker", () => {
  it("refreshes the news stocks when the timer fires in market hours", async () => {
    const db = localD1(); const now = at("2026-11-25T10:00:00+05:30");
    const r = await worker.scheduled({}, { DB: db }, { now, fetch: yahoo(now.getTime() / 1000 - 20), sleep: async () => {} });
    expect(r.written).toBeGreaterThan(0);
    expect(db.db.prepare("select count(*) n from quotes where as_of = '2026-11-25T09:59:40+05:30'").get().n).toBe(r.written);
  });
  it("does nothing outside market hours (no calls, no writes)", async () => {
    let n = 0; const db = localD1();
    const r = await worker.scheduled({}, { DB: db }, { now: at("2026-11-25T21:00:00+05:30"), fetch: async () => { n++; return yahoo(1)(); }, sleep: async () => {} });
    expect(n).toBe(0); expect(r.written).toBe(0);
  });
  it("has a 5-minute timer that covers market hours only, and is not a web endpoint", () => {
    const toml = readFileSync(new URL("../quotes/wrangler.toml", import.meta.url), "utf8");
    expect(toml).toMatch(/crons\s*=\s*\[\s*"\*\/5 3-10 \* \* 1-5"\s*\]/);
    expect(toml).toMatch(/workers_dev\s*=\s*false/);
    expect(typeof worker.fetch).toBe("undefined");
  });
});
