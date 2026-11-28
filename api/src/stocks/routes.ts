// Stock routes: search, one stock, its history, and load-on-demand for a symbol we hold nothing for.
import { HistoryPost, type LoadJob, QUOTE_MAX_AGE_SECONDS } from "@stockpilot/contract";
import { Hono } from "hono";
import { type GithubBot, githubFromEnv } from "../../../adapters/src/github";
import { type Ctx, istDay, istText, rawBody } from "../app";
import { getJob, isPaused, jobKey } from "../jobs/runtime";
import { readQuote, watch } from "../quotes/quotes";
import { dispatchJob, queueJob } from "../schedule/tick";
import { findStock, loadUniverse, readHistory, searchUniverse, storeHistory } from "./stocks";

const SYMBOL = /^[A-Z0-9][A-Z0-9&-]{0,19}$/;
/** The load Job is the history Job with the symbol as its subject; history.yml runs it. */
export const LOAD_KIND = "history";

export async function loadState(ctx: Ctx, symbol: string): Promise<LoadJob | null> {
  const key = jobKey(LOAD_KIND, symbol, istDay(ctx.now()));
  const job = await getJob(ctx, key);
  if (!job) return null;
  return { state: job.status as LoadJob["state"], key, error: job.error ?? null };
}

export function stocksRoutes(ctx: Ctx, opts: { github?: GithubBot } = {}) {
  const app = new Hono();

  app.get("/api/stocks/search", ctx.guard.person, async (c) => {
    const hits = searchUniverse(await loadUniverse(ctx.d1), c.req.query("q") ?? "");
    return c.json({
      hits: hits.map((u) => ({
        symbol: u.symbol,
        exchange: u.exchange,
        segment: u.segment,
        name: u.name,
        status: u.status,
      })),
    });
  });

  // For the universe Job: it keeps stocks that dropped off the lists, marked delisted.
  app.get("/api/stocks/universe", ctx.guard.ingest, async (c) =>
    c.json({ rows: await loadUniverse(ctx.d1) }),
  );

  app.post("/api/stocks/history", ctx.guard.ingest, async (c) => {
    let body: unknown;
    try {
      body = JSON.parse(rawBody(c));
    } catch {
      return c.json({ error: "bad body" }, 400);
    }
    const post = HistoryPost.safeParse(body);
    if (!post.success) return c.json({ error: "bad body" }, 400);
    return c.json({ stored: await storeHistory(ctx.d1, post.data) });
  });

  app.get("/api/stocks/:symbol", ctx.guard.person, async (c) => {
    const symbol = c.req.param("symbol").toUpperCase();
    const entry = await findStock(ctx.d1, symbol);
    const exchange = entry?.exchange ?? "NSE";
    if (entry) await watch(ctx, symbol, exchange);
    const stats = (await ctx.d1
      .prepare(
        "select count(*) as days, min(date) as first, max(date) as last from stock_history where symbol = ? and exchange = ?",
      )
      .bind(symbol, exchange)
      .first()) as { days: number; first: string | null; last: string | null };
    const last = stats.days
      ? ((await readHistory(ctx.d1, symbol, exchange, stats.last ?? undefined)).at(-1) ?? null)
      : null;
    return c.json({
      symbol,
      known: entry !== null || stats.days > 0,
      entry: entry
        ? {
            symbol: entry.symbol,
            exchange: entry.exchange,
            segment: entry.segment,
            name: entry.name,
            status: entry.status,
            isin: entry.isin,
          }
        : null,
      last,
      history: { days: stats.days, first: stats.first, last: stats.last },
      quote: await readQuote(ctx, symbol, QUOTE_MAX_AGE_SECONDS),
      load: await loadState(ctx, symbol),
    });
  });

  app.get("/api/stocks/:symbol/history", ctx.guard.person, async (c) => {
    const symbol = c.req.param("symbol").toUpperCase();
    const entry = await findStock(ctx.d1, symbol);
    const from = c.req.query("from");
    return c.json({
      symbol,
      rows: await readHistory(ctx.d1, symbol, entry?.exchange ?? "NSE", from),
    });
  });

  // An unknown (or empty) symbol starts one load Job. Pressing again while it runs shows the same Job.
  app.post("/api/stocks/:symbol/load", ctx.guard.person, async (c) => {
    const symbol = c.req.param("symbol").toUpperCase();
    if (!SYMBOL.test(symbol)) return c.json({ error: "not a stock symbol" }, 400);
    const existing = await loadState(ctx, symbol);
    if (existing && existing.state !== "failed") return c.json(existing);
    if (await isPaused(ctx, LOAD_KIND)) return c.json({ error: `${LOAD_KIND} is paused` }, 423);
    const bot = opts.github ?? githubFromEnv(ctx.env as Record<string, string | undefined>);
    if (!bot) return c.json({ error: "the dispatcher has no bot key yet" }, 503);
    const day = istDay(ctx.now());
    const key = jobKey(LOAD_KIND, symbol, day);
    if (existing) {
      await ctx.d1
        .prepare(
          "update job_runs set status = 'queued', queued_at = ?, dispatched_at = null, dispatch_count = 0, attempts = 0, error = null, retry_at = null where key = ?",
        )
        .bind(istText(ctx.now()), key)
        .run();
    } else await queueJob(ctx, { kind: LOAD_KIND, subject: symbol, day, from: day, to: day });
    try {
      await dispatchJob(
        { github: bot, workflowFor: () => "history.yml" },
        { kind: LOAD_KIND, subject: symbol, day, range_from: day, range_to: day },
      );
      await ctx.d1
        .prepare(
          "update job_runs set dispatched_at = ?, dispatch_count = dispatch_count + 1 where key = ?",
        )
        .bind(istText(ctx.now()), key)
        .run();
    } catch {
      // left queued: the 5-minute tick dispatches it
    }
    return c.json({ state: "queued", key, error: null } satisfies LoadJob, 202);
  });

  return app;
}

export default (ctx: Ctx) => stocksRoutes(ctx);
