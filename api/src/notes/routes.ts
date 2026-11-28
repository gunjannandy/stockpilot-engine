// Notes: post-mortems on missed calls (the Job's two doors and the person's read for Record) and the nightly note
// (written back by the scheduled task with its own key; read by the person).
import {
  type AnalyseCall,
  missed,
  NightlyNote,
  nightlyNoteCheck,
  PostmortemRow,
  PRICE_SLACK_DAYS,
  postmortemRowCheck,
  SCORE_DAYS,
} from "@stockpilot/contract";
import { Hono } from "hono";
import { type Ctx, istDay, istText, rawBody } from "../app";
import { readImpact } from "../news/impact";
import { findStock } from "../stocks/stocks";
import { taskKey } from "../summary/key";

const NIFTY = "NIFTY 50";
const DUE_LIMIT = 10;
const addDays = (day: string, n: number) =>
  new Date(Date.parse(`${day}T00:00:00Z`) + n * 86400_000).toISOString().slice(0, 10);

type Close = { date: string; close: number };

async function closeOnOrBefore(
  ctx: Pick<Ctx, "d1">,
  symbol: string,
  exchange: string,
  day: string,
): Promise<number | null> {
  const r = (await ctx.d1
    .prepare(
      "select date, close from stock_history where symbol = ? and exchange = ? and date <= ? and close is not null order by date desc limit 1",
    )
    .bind(symbol, exchange, day)
    .first()) as Close | null;
  if (!r) return null;
  return Date.parse(day) - Date.parse(r.date) <= PRICE_SLACK_DAYS * 86400_000 ? r.close : null;
}

/** Excess return over the Nifty 50 across [from, to], percent points, or null when a close is missing. */
export async function excessOver(
  ctx: Pick<Ctx, "d1">,
  symbol: string,
  exchange: string,
  from: string,
  to: string,
) {
  const [s0, s1] = [
    await closeOnOrBefore(ctx, symbol, exchange, from),
    await closeOnOrBefore(ctx, symbol, exchange, to),
  ];
  const nx = (await ctx.d1
    .prepare("select exchange from stock_history where symbol = ? limit 1")
    .bind(NIFTY)
    .first()) as { exchange: string } | null;
  const [n0, n1] = nx
    ? [
        await closeOnOrBefore(ctx, NIFTY, nx.exchange, from),
        await closeOnOrBefore(ctx, NIFTY, nx.exchange, to),
      ]
    : [null, null];
  if (!s0 || !s1 || !n0 || !n1) return null;
  const stock = (s1 / s0 - 1) * 100;
  const nifty = (n1 / n0 - 1) * 100;
  return { stock_pct: round(stock), nifty_pct: round(nifty), excess_pct: round(stock - nifty) };
}
const round = (x: number) => Math.round(x * 10) / 10;

type CallRow = Pick<AnalyseCall, "symbol" | "day" | "call" | "chance_pct" | "summary_en"> & {
  key: string;
  reasons: string;
  risks: string;
};

export default function routes(ctx: Ctx) {
  const app = new Hono();

  // Missed calls whose three-month window has ended and that have no post-mortem yet, oldest first.
  app.get("/api/postmortem/due", ctx.guard.ingest, async (c) => {
    const today = istDay(ctx.now());
    const r = (await ctx.d1
      .prepare(
        `select key, symbol, day, call, chance_pct, summary_en, reasons, risks from analyse_calls
         where call in ('buy','avoid') and day <= ? and key not in (select call_key from postmortems)
         order by day limit 60`,
      )
      .bind(addDays(today, -SCORE_DAYS))
      .all()) as { results: CallRow[] };
    const calls = [];
    for (const k of r.results) {
      if (calls.length >= DUE_LIMIT) break;
      const end = addDays(k.day, SCORE_DAYS);
      const entry = await findStock(ctx.d1, k.symbol);
      const got = await excessOver(ctx, k.symbol, entry?.exchange ?? "NSE", k.day, end);
      if (!got || !missed(k.call as "buy" | "avoid", got.excess_pct)) continue;
      const news = (
        await readImpact(ctx.d1, { symbols: [k.symbol], since: `${k.day}T00:00:00`, limit: 12 })
      )
        .filter((i) => !i.sector_only && i.judged_at.slice(0, 10) <= end)
        .slice(0, 6)
        .map((i) => ({ direction: i.direction, why_en: i.why_en, title: "" }));
      calls.push({
        ...k,
        ...got,
        end_day: end,
        reasons: JSON.parse(k.reasons) as unknown,
        risks: JSON.parse(k.risks) as unknown,
        news_after: news,
      });
    }
    return c.json({ calls });
  });

  app.post("/api/postmortem/row", ctx.guard.ingest, async (c) => {
    let body: unknown;
    try {
      body = JSON.parse(rawBody(c));
    } catch {
      return c.json({ error: "bad body" }, 400);
    }
    const req = PostmortemRow.safeParse(body);
    if (!req.success) return c.json({ error: "bad body" }, 400);
    const refused = postmortemRowCheck(req.data);
    if (refused) return c.json({ error: refused }, 422);
    const k = req.data;
    // One row per call: a second write for the same call is ignored.
    const res = (await ctx.d1
      .prepare(
        "insert or ignore into postmortems (call_key, symbol, day, call, excess_pct, cause, why_en, why_bn, evidence, source, model, stored_at) values (?,?,?,?,?,?,?,?,?,?,?,?)",
      )
      .bind(
        k.call_key,
        k.symbol,
        k.day,
        k.call,
        k.excess_pct,
        k.cause,
        k.why_en,
        k.why_bn,
        JSON.stringify(k.evidence),
        k.source,
        k.model,
        istText(ctx.now()),
      )
      .run()) as { meta?: { changes?: number } };
    return c.json({ written: res.meta?.changes ?? 0 });
  });

  // For Record: the newest post-mortems, or one stock's.
  app.get("/api/postmortems", ctx.guard.person, async (c) => {
    const symbol = c.req.query("symbol")?.toUpperCase();
    const r = (await ctx.d1
      .prepare(
        `select call_key, symbol, day, call, excess_pct, cause, why_en, why_bn, evidence, source from postmortems ${symbol ? "where symbol = ?" : ""} order by stored_at desc limit 100`,
      )
      .bind(...(symbol ? [symbol] : []))
      .all()) as { results: (Record<string, unknown> & { evidence: string })[] };
    return c.json({
      postmortems: r.results.map((x) => ({ ...x, evidence: JSON.parse(x.evidence) as unknown })),
    });
  });

  // The nightly note: the scheduled task writes it back with its own key; one note per day, a rewrite replaces it.
  app.post("/api/notes/nightly", taskKey(ctx), async (c) => {
    const req = NightlyNote.safeParse(await c.req.json().catch(() => undefined));
    if (!req.success) return c.json({ error: "bad body" }, 400);
    const refused = nightlyNoteCheck(req.data);
    if (refused) return c.json({ error: refused }, 422);
    await ctx.d1
      .prepare(
        "insert or replace into nightly_notes (day, text_en, text_bn, stored_at) values (?,?,?,?)",
      )
      .bind(req.data.day, req.data.text_en, req.data.text_bn, istText(ctx.now()))
      .run();
    return c.json({ ok: true });
  });

  app.get("/api/notes/nightly", ctx.guard.person, async (c) => {
    const r = await ctx.d1
      .prepare("select day, text_en, text_bn from nightly_notes order by day desc limit 1")
      .first();
    return c.json({ note: r ?? null });
  });

  return app;
}
