// Analyse: the Job's read of public inputs for one stock (facts, daily history, news impact), the Job's write of one
// call per stock and day, and the person's read of that call. Nothing here knows what anyone holds.
import { AnalyseCall, analyseCallCheck } from "@stockpilot/contract";
import { Hono } from "hono";
import { type GithubBot, githubFromEnv } from "../../../adapters/src/github";
import { type Ctx, istDay, istText, rawBody } from "../app";
import { expectedSeconds, getJob, isPaused, jobKey } from "../jobs/runtime";
import { readImpact } from "../news/impact";
import { dispatchJob, queueJob } from "../schedule/tick";
import { findStock, readHistory } from "../stocks/stocks";
import { benchRoutes } from "./bench";
import { fundcallRoutes } from "./fundcall";

const KIND = "analyse";
const SYMBOL = /^[A-Z0-9][A-Z0-9&-]{0,19}$/;
const HISTORY_DAYS = 400;
const NEWS_WEEKS = 3;

type Stored = {
  symbol: string;
  day: string;
  call: string;
  chance_pct: number;
  source: string;
  summary_en: string | null;
  summary_bn: string | null;
  reasons: string;
  risks: string;
  model: string | null;
  note: string | null;
  stored_at: string;
};

const shape = (r: Stored) => ({
  ...r,
  reasons: JSON.parse(r.reasons) as unknown,
  risks: JSON.parse(r.risks) as unknown,
});

async function pointerRows(ctx: Ctx, dataset: string, where = "", bind: unknown[] = []) {
  const p = (await ctx.d1
    .prepare("select run_id from pointers where dataset = ?")
    .bind(dataset)
    .first()) as { run_id: string } | null;
  if (!p) return [];
  const r = (await ctx.d1
    .prepare(
      `select body from dataset_rows where dataset = ? and run_id = ? ${where} order by seq limit 600`,
    )
    .bind(dataset, p.run_id, ...bind)
    .all()) as { results: { body: string }[] };
  return r.results.map((x) => JSON.parse(x.body) as Record<string, unknown>);
}

export function analyseRoutes(ctx: Ctx, opts: { github?: GithubBot } = {}) {
  const app = new Hono();
  app.route("/", benchRoutes(ctx));
  app.route("/", fundcallRoutes(ctx));

  app.get("/api/analyse/inputs/:symbol", ctx.guard.ingest, async (c) => {
    const symbol = c.req.param("symbol").toUpperCase();
    if (!SYMBOL.test(symbol)) return c.json({ error: "bad symbol" }, 400);
    const entry = await findStock(ctx.d1, symbol);
    const exchange = entry?.exchange ?? "NSE";
    const from = new Date(ctx.now().getTime() - HISTORY_DAYS * 86400_000)
      .toISOString()
      .slice(0, 10);
    const history = (await readHistory(ctx.d1, symbol, exchange, from)).map((r) => ({
      date: r.date,
      close: r.close,
    }));
    const [facts] = await pointerRows(ctx, "facts", "and json_extract(body, '$.symbol') = ?", [
      symbol,
    ]);
    const impacts = await readImpact(ctx.d1, {
      symbols: [symbol],
      since: new Date(ctx.now().getTime() - NEWS_WEEKS * 7 * 86400_000).toISOString(),
      limit: 20,
    });
    const items = new Map(
      (await pointerRows(ctx, "news_items")).map((i) => [i.id as string, i.title as string]),
    );
    const news = impacts
      .filter((i) => !i.sector_only)
      .map((i) => ({
        id: i.id,
        title: items.get(i.item_id) ?? "",
        direction: i.direction,
        size: i.size,
        why_en: i.why_en,
      }));
    return c.json({ facts: facts ?? null, history, news });
  });

  app.post("/api/analyse/call", ctx.guard.ingest, async (c) => {
    let body: unknown;
    try {
      body = JSON.parse(rawBody(c));
    } catch {
      return c.json({ error: "bad body" }, 400);
    }
    const req = AnalyseCall.safeParse(body);
    if (!req.success) return c.json({ error: "bad body" }, 400);
    const refused = analyseCallCheck(req.data);
    if (refused) return c.json({ error: refused }, 422);
    const k = req.data;
    await ctx.d1
      .prepare(
        "insert or replace into analyse_calls (key, symbol, day, call, chance_pct, source, summary_en, summary_bn, reasons, risks, model, note, stored_at) values (?,?,?,?,?,?,?,?,?,?,?,?,?)",
      )
      .bind(
        `${k.symbol}|${k.day}`,
        k.symbol,
        k.day,
        k.call,
        k.chance_pct,
        k.source,
        k.summary_en,
        k.summary_bn,
        JSON.stringify(k.reasons),
        JSON.stringify(k.risks),
        k.model,
        k.note,
        istText(ctx.now()),
      )
      .run();
    return c.json({ ok: true });
  });

  // The newest call for a stock; the browser adds the tax and "if you act" lines on the device.
  app.get("/api/analyse/:symbol", ctx.guard.person, async (c) => {
    const symbol = c.req.param("symbol").toUpperCase();
    const r = (await ctx.d1
      .prepare(
        "select symbol, day, call, chance_pct, source, summary_en, summary_bn, reasons, risks, model, note, stored_at from analyse_calls where symbol = ? order by day desc limit 1",
      )
      .bind(symbol)
      .first()) as Stored | null;
    const job = await getJob(ctx, jobKey(KIND, symbol, istDay(ctx.now())));
    return c.json({
      symbol,
      call: r ? shape(r) : null,
      job: job ? { state: job.status, error: job.error ?? null } : null,
      // The progress bar's length: the middle of past runs, or null before there are any.
      expected_seconds: await expectedSeconds(ctx, KIND),
    });
  });

  // The Analyse button: the Job is dispatched at once, not at the next tick. A second press shows the same Job.
  app.post("/api/analyse/:symbol/run", ctx.guard.person, async (c) => {
    const symbol = c.req.param("symbol").toUpperCase();
    if (!SYMBOL.test(symbol)) return c.json({ error: "bad symbol" }, 400);
    const day = istDay(ctx.now());
    const key = jobKey(KIND, symbol, day);
    const existing = await getJob(ctx, key);
    if (existing && existing.status !== "failed")
      return c.json({
        state: existing.status,
        key,
        expected_seconds: await expectedSeconds(ctx, KIND),
      });
    if (await isPaused(ctx, KIND)) return c.json({ error: `${KIND} is paused` }, 423);
    const bot = opts.github ?? githubFromEnv(ctx.env as Record<string, string | undefined>);
    if (!bot) return c.json({ error: "the dispatcher has no bot key yet" }, 503);
    if (existing)
      await ctx.d1
        .prepare(
          "update job_runs set status = 'queued', queued_at = ?, dispatched_at = null, dispatch_count = 0, attempts = 0, error = null, retry_at = null where key = ?",
        )
        .bind(istText(ctx.now()), key)
        .run();
    else await queueJob(ctx, { kind: KIND, subject: symbol, day, from: day, to: day });
    try {
      await dispatchJob(
        { github: bot },
        { kind: KIND, subject: symbol, day, range_from: day, range_to: day },
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
    return c.json(
      { state: "queued", key, expected_seconds: await expectedSeconds(ctx, KIND) },
      202,
    );
  });

  return app;
}

export default (ctx: Ctx) => analyseRoutes(ctx);
