import { z } from "zod";
import { IsoDate, IstTime } from "../core/time";

/** The stock pages' data shapes (v3 STOCKDATA). Public market data only. */

export const EXCHANGES = ["NSE", "BSE"] as const;
export const SEGMENTS = ["NSE", "NSE_SME", "BSE", "BSE_SME"] as const;

/** One row of the `universe` dataset: a listed (or once-listed) stock. Delisted and renamed stocks stay. */
export const UniverseRow = z.object({
  id: z.string().min(1),
  symbol: z.string().min(1),
  exchange: z.enum(EXCHANGES),
  segment: z.enum(SEGMENTS),
  name: z.string().min(1),
  isin: z.string(),
  /** Lower-case search words joined by `|`. */
  aliases: z.string(),
  status: z.enum(["listed", "delisted"]),
});
export type UniverseRow = z.infer<typeof UniverseRow>;

/** One day's prices for one stock, as the exchange printed them. */
export const CloseRow = z.object({
  date: IsoDate,
  open: z.number().nullable(),
  high: z.number().nullable(),
  low: z.number().nullable(),
  close: z.number(),
  prev_close: z.number().nullable(),
  volume: z.number().nullable(),
});
export type CloseRow = z.infer<typeof CloseRow>;

/** What a Job posts to `POST /api/stocks/history`: days for one stock. */
export const HistoryPost = z.object({
  symbol: z.string().min(1),
  exchange: z.enum(EXCHANGES),
  rows: z.array(CloseRow).max(5000),
});
export type HistoryPost = z.infer<typeof HistoryPost>;

/** A price move this big in one day (40%) must be explained by a corporate action, or the series is held back. */
export const MOVE_LIMIT = 0.4;
/** Share of stocks that may be held back for an unexplained move before the run fails. */
export const HELD_BACK_LIMIT = 0.02;

/** The first day whose close is more than `limit` away from the day before, ignoring `explained` dates. */
export function unexplainedMove(
  rows: { date: string; close: number }[],
  explained: ReadonlySet<string> = new Set(),
  limit = MOVE_LIMIT,
): { date: string; from: number; to: number } | null {
  const sorted = [...rows].sort((a, b) => a.date.localeCompare(b.date));
  for (let i = 1; i < sorted.length; i++) {
    const a = sorted[i - 1];
    const b = sorted[i];
    if (!a || !b || a.close <= 0 || explained.has(b.date)) continue;
    if (Math.abs(b.close / a.close - 1) > limit)
      return { date: b.date, from: a.close, to: b.close };
  }
  return null;
}

export const SearchHit = z.object({
  symbol: z.string(),
  exchange: z.enum(EXCHANGES),
  segment: z.enum(SEGMENTS),
  name: z.string(),
  status: z.enum(["listed", "delisted"]),
});
export const SearchResponse = z.object({ hits: z.array(SearchHit) });
export type SearchResponse = z.infer<typeof SearchResponse>;

/** How old a cached quote may be and still be shown, and the cut-off for "market hours". */
export const QUOTE_MAX_AGE_SECONDS = 600;

export const Quote = z.object({
  symbol: z.string(),
  price: z.number(),
  prev_close: z.number().nullable(),
  at: IstTime,
  /** Seconds since `at`, so the screen can show the age. */
  age_seconds: z.number().int().min(0),
});
export type Quote = z.infer<typeof Quote>;
export const QuotesResponse = z.object({
  quotes: z.array(Quote),
  /** Symbols asked for that have no quote within the age limit. */
  stale: z.array(z.string()),
  max_age_seconds: z.number().int(),
});

/** A Job's life, as the page shows it. */
export const LoadJob = z.object({
  state: z.enum(["queued", "running", "done", "failed"]),
  key: z.string(),
  error: z.string().nullable(),
});
export const StockResponse = z.object({
  symbol: z.string(),
  known: z.boolean(),
  entry: SearchHit.extend({ isin: z.string() }).nullable(),
  last: CloseRow.nullable(),
  /** Days of history held, first and last day. */
  history: z.object({
    days: z.number().int(),
    first: IsoDate.nullable(),
    last: IsoDate.nullable(),
  }),
  quote: Quote.nullable(),
  /** A load Job in flight or just finished, if any. */
  load: LoadJob.nullable(),
});
export type StockResponse = z.infer<typeof StockResponse>;
export const HistoryResponse = z.object({ symbol: z.string(), rows: z.array(CloseRow) });

/** The stock routes. The web client and the Python Jobs read this table. */
export const stockRoutes = {
  stock_search: {
    method: "GET",
    path: "/api/stocks/search?q=",
    auth: "person",
    response: SearchResponse,
  },
  stock_get: {
    method: "GET",
    path: "/api/stocks/:symbol",
    auth: "person",
    response: StockResponse,
  },
  stock_history: {
    method: "GET",
    path: "/api/stocks/:symbol/history?from=",
    auth: "person",
    response: HistoryResponse,
  },
  stock_load: {
    method: "POST",
    path: "/api/stocks/:symbol/load",
    auth: "person",
    response: LoadJob,
  },
  stock_quotes: {
    method: "GET",
    path: "/api/quotes?symbols=",
    auth: "person",
    response: QuotesResponse,
  },
  stock_history_post: {
    method: "POST",
    path: "/api/stocks/history",
    auth: "ingest",
    request: HistoryPost,
  },
  stock_universe: {
    method: "GET",
    path: "/api/stocks/universe",
    auth: "ingest",
    response: z.object({ rows: z.array(UniverseRow) }),
  },
} as const;

export function universeRowCheck(r: Record<string, unknown>): string | null {
  return typeof r.symbol === "string" &&
    r.symbol.trim() &&
    typeof r.name === "string" &&
    r.name.trim()
    ? null
    : "symbol and name are required";
}
export type LoadJob = z.infer<typeof LoadJob>;

/** One row a day for the `history` dataset: what the daily run did. The prices themselves go to `POST /api/stocks/history`. */
export const HistoryRun = z.object({
  id: z.string().min(1),
  day: IsoDate,
  stocks: z.number().int().min(0),
  held_back: z.number().int().min(0),
});
export type HistoryRun = z.infer<typeof HistoryRun>;
