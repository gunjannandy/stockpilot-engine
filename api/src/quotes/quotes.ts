// Near-live quotes: a cron duty fills `quote_cache` in market hours; routes answer from it within an age limit.
import { QUOTE_MAX_AGE_SECONDS, type Quote } from "@stockpilot/contract";
import { type Ctx, istText } from "../app";

type Core = Pick<Ctx, "d1" | "now">;

export async function writeQuotes(
  ctx: Core,
  quotes: { symbol: string; price: number; prev_close: number | null }[],
): Promise<number> {
  const now = ctx.now();
  const at = istText(now);
  const stmt = ctx.d1.prepare(
    `insert into quote_cache (symbol, price, prev_close, at, at_ms) values (?, ?, ?, ?, ?)
     on conflict(symbol) do update set price = excluded.price, prev_close = excluded.prev_close,
       at = excluded.at, at_ms = excluded.at_ms`,
  );
  for (let i = 0; i < quotes.length; i += 50)
    await ctx.d1.batch(
      quotes
        .slice(i, i + 50)
        .map((q) => stmt.bind(q.symbol.toUpperCase(), q.price, q.prev_close, at, now.getTime())),
    );
  return quotes.length;
}

/** The cached quote if it is no older than `maxAge` seconds, with its age; otherwise null. */
export async function readQuote(
  ctx: Core,
  symbol: string,
  maxAge = QUOTE_MAX_AGE_SECONDS,
): Promise<Quote | null> {
  const r = (await ctx.d1
    .prepare("select symbol, price, prev_close, at, at_ms from quote_cache where symbol = ?")
    .bind(symbol.toUpperCase())
    .first()) as {
    symbol: string;
    price: number;
    prev_close: number | null;
    at: string;
    at_ms: number;
  } | null;
  if (!r) return null;
  const age = Math.max(0, Math.round((ctx.now().getTime() - r.at_ms) / 1000));
  if (age > maxAge) return null;
  return {
    symbol: r.symbol,
    price: r.price,
    prev_close: r.prev_close,
    at: r.at as Quote["at"],
    age_seconds: age,
  };
}

export const MAX_PER_RUN = 12; // free Worker: 50 subrequests a run
const WATCH_DAYS = 2;

export async function watch(ctx: Core, symbol: string, exchange = "NSE") {
  await ctx.d1
    .prepare(
      "insert into quote_watch (symbol, exchange, asked_ms) values (?, ?, ?) on conflict(symbol) do update set asked_ms = excluded.asked_ms",
    )
    .bind(symbol.toUpperCase(), exchange, ctx.now().getTime())
    .run();
}

/** Weekdays 09:15 to 15:30 IST. */
export function marketOpen(now: Date): boolean {
  const ist = new Date(now.getTime() + 5.5 * 3600_000);
  const day = ist.getUTCDay();
  const mins = ist.getUTCHours() * 60 + ist.getUTCMinutes();
  return day >= 1 && day <= 5 && mins >= 9 * 60 + 15 && mins <= 15 * 60 + 30;
}

export function parseYahoo(json: unknown): { price: number; prev_close: number | null } | null {
  const m = (json as { chart?: { result?: { meta?: Record<string, unknown> }[] } })?.chart
    ?.result?.[0]?.meta;
  if (!m || typeof m.regularMarketPrice !== "number") return null;
  return {
    price: m.regularMarketPrice,
    prev_close: typeof m.chartPreviousClose === "number" ? m.chartPreviousClose : null,
  };
}

type Fetch = (url: string) => Promise<{ ok: boolean; json(): Promise<unknown> }>;
/** One run: refresh the watched symbols, stalest first. Returns how many were written. */
export async function refreshQuotes(ctx: Core, fetcher: Fetch = (u) => fetch(u)): Promise<number> {
  if (!marketOpen(ctx.now())) return 0;
  const since = ctx.now().getTime() - WATCH_DAYS * 86_400_000;
  const w = (await ctx.d1
    .prepare(
      `select w.symbol, w.exchange from quote_watch w left join quote_cache q on q.symbol = w.symbol
       where w.asked_ms >= ? order by coalesce(q.at_ms, 0) limit ?`,
    )
    .bind(since, MAX_PER_RUN)
    .all()) as { results: { symbol: string; exchange: string }[] };
  const got: { symbol: string; price: number; prev_close: number | null }[] = [];
  for (const s of w.results) {
    try {
      const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(s.symbol)}.${s.exchange === "BSE" ? "BO" : "NS"}?range=1d&interval=1m`;
      const res = await fetcher(url);
      const q = res.ok ? parseYahoo(await res.json()) : null;
      if (q) got.push({ symbol: s.symbol, ...q });
    } catch {
      // one symbol failing leaves the others
    }
  }
  return writeQuotes(ctx, got);
}
