// T15: near-live prices for the stocks in the news. Yahoo first, NSE's quote API as a bonus.
// Shared by the quote Worker (every 5 minutes in market hours) and the stock page's refresh-on-open.
// Public data only. Every row keeps its own as_of, so the page can always say how old a price is.
import { WARN_AT, STOP_AT } from "../../ingest/tables.js";

const IST_MS = 5.5 * 3600 * 1000;
export const SPACING_MS = 400;          // gap between source calls
export const MAX_SYMBOLS = 12;          // free Worker: 50 subrequests a run; 12 x (Yahoo + NSE) + cookie + D1 stays under it
export const STALE_YAHOO_SECONDS = 15 * 60;
const NEWS_DAYS = 2;
const UA = "Mozilla/5.0 (compatible; stockpilot)";
const istISO = (d) => new Date(d.getTime() + IST_MS).toISOString().replace(/\.\d+Z$/, "+05:30");

// Weekdays 09:15 to 15:30 IST. Exchange holidays are not known here; a holiday just yields an old as_of, shown as such.
export function marketOpen(date) {
  const ist = new Date(date.getTime() + IST_MS);
  const day = ist.getUTCDay();
  const mins = ist.getUTCHours() * 60 + ist.getUTCMinutes();
  return day >= 1 && day <= 5 && mins >= 9 * 60 + 15 && mins <= 15 * 60 + 30;
}

export function parseYahoo(json) {
  const m = json?.chart?.result?.[0]?.meta;
  if (!m || typeof m.regularMarketPrice !== "number" || typeof m.regularMarketTime !== "number") return null;
  return { price: m.regularMarketPrice, prev_close: typeof m.chartPreviousClose === "number" ? m.chartPreviousClose : m.regularMarketPrice, as_of: istISO(new Date(m.regularMarketTime * 1000)) };
}

const MONTHS = { Jan: "01", Feb: "02", Mar: "03", Apr: "04", May: "05", Jun: "06", Jul: "07", Aug: "08", Sep: "09", Oct: "10", Nov: "11", Dec: "12" };
export function parseNse(json, now) {
  const p = json?.priceInfo;
  if (!p || typeof p.lastPrice !== "number") return null;
  const m = /^(\d{2})-([A-Za-z]{3})-(\d{4}) (\d{2}:\d{2}:\d{2})$/.exec(p.lastUpdateTime || "");
  const as_of = m && MONTHS[m[2]] ? `${m[3]}-${MONTHS[m[2]]}-${m[1]}T${m[4]}+05:30` : istISO(now);
  return { price: p.lastPrice, prev_close: typeof p.previousClose === "number" ? p.previousClose : p.lastPrice, as_of };
}

// Stocks tagged on news from the last two days, most recent news first, each once.
export async function newsSymbols(db, now, { limit = MAX_SYMBOLS } = {}) {
  const since = istISO(new Date(now.getTime() - NEWS_DAYS * 86400000));
  const { results } = await db.prepare(
    `select t.symbol, t.exchange, max(i.published_at) as latest from news_tags t join news_items i on i.id = t.item_id
     where i.published_at >= ? group by t.symbol, t.exchange order by latest desc, t.symbol limit ?`).bind(since, limit).all();
  return results.map(({ symbol, exchange }) => ({ symbol, exchange }));
}

const getJson = async (fetch, url, headers) => {
  try { const r = await fetch(url, { headers: { "user-agent": UA, ...headers } }); return r.ok ? await r.json() : null; } catch { return null; }
};
const yahooOf = async (fetch, s) =>
  parseYahoo(await getJson(fetch, `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(s.symbol)}.${s.exchange === "BSE" ? "BO" : "NS"}?range=1d&interval=1m`));

// NSE wants a cookie from its home page first; one cookie serves the whole run.
function nseSession(fetch) {
  let cookie;
  return async (s, now) => {
    if (cookie === undefined) {
      try { const h = await fetch("https://www.nseindia.com/", { headers: { "user-agent": UA, accept: "text/html" } }); cookie = (h.headers?.getSetCookie?.() || []).map((c) => c.split(";")[0]).join("; "); } catch { cookie = ""; }
    }
    return parseNse(await getJson(fetch, `https://www.nseindia.com/api/quote-equity?symbol=${encodeURIComponent(s.symbol)}`, { cookie, accept: "application/json", referer: "https://www.nseindia.com/" }), now);
  };
}

// Refresh the given stocks. Returns { written, failed: [symbol], stopped }.
export async function refreshQuotes({ db, symbols, fetch, now, sleep = (ms) => new Promise((r) => setTimeout(r, ms)), minAgeSeconds = 0 }) {
  const day = new Date(now.getTime() + IST_MS).toISOString().slice(0, 10);
  const list = symbols.slice(0, MAX_SYMBOLS);
  const budget = await db.prepare("select writes from write_budget where day = ?").bind(day).first();
  let writes = budget?.writes ?? 0;
  if (writes >= STOP_AT) return { written: 0, failed: [], stopped: true };

  const stored = new Map();
  if (list.length) {
    const { results } = await db.prepare(`select symbol, exchange, as_of from quotes where symbol in (${list.map(() => "?").join(",")})`).bind(...list.map((s) => s.symbol)).all();
    results.forEach((r) => stored.set(r.symbol + "|" + r.exchange, r.as_of));
  }
  const nse = nseSession(fetch);
  const rows = [], failed = [];
  let first = true;
  for (const s of list) {
    const was = stored.get(s.symbol + "|" + s.exchange);
    if (minAgeSeconds && was && (now.getTime() - Date.parse(was)) / 1000 < minAgeSeconds) continue;
    if (!first) await sleep(SPACING_MS);
    first = false;
    let q = await yahooOf(fetch, s), source = "yahoo";
    const old = !q || (now.getTime() - Date.parse(q.as_of)) / 1000 > STALE_YAHOO_SECONDS;
    if (old && s.exchange === "NSE") {
      await sleep(SPACING_MS);
      const n = await nse(s, now);
      if (n && (!q || Date.parse(n.as_of) > Date.parse(q.as_of))) { q = n; source = "nse"; }
    }
    if (q) rows.push({ symbol: s.symbol, exchange: s.exchange, ...q, source }); else failed.push(s.symbol);
  }
  if (rows.length) {
    const stamp = istISO(now);
    await db.batch([
      ...rows.map((r) => db.prepare(
        "insert into quotes (symbol, exchange, price, prev_close, as_of, source) values (?, ?, ?, ?, ?, ?) " +
        "on conflict(symbol, exchange) do update set price = excluded.price, prev_close = excluded.prev_close, as_of = excluded.as_of, source = excluded.source where excluded.as_of >= quotes.as_of")
        .bind(r.symbol, r.exchange, r.price, r.prev_close, r.as_of, r.source)),
      db.prepare("insert into write_budget (day, writes, warn_at, stop_at, updated_at) values (?, ?, ?, ?, ?) on conflict(day) do update set writes = excluded.writes, updated_at = excluded.updated_at")
        .bind(day, writes + rows.length, WARN_AT, STOP_AT, stamp),
    ]);
  }
  return { written: rows.length, failed, stopped: false };
}
