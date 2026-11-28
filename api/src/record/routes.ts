// Record: the scoring Job's door (scores of ended calls, adding-value figures), what it needs to score, and the track
// record read from the scored calls. Scores are only ever inserted; a repeat is ignored.
import {
  addingValue,
  RecordRequest,
  type RecordResponse,
  recordVerdict,
  type TrackLine,
  trackSentence,
  WINDOW_DAYS,
} from "@stockpilot/contract";
import { Hono } from "hono";
import { type Ctx, istDay, rawBody } from "../app";

const SLACK = 7;

export default function routes(ctx: Ctx) {
  const app = new Hono();

  /** Calls whose window has ended and that have no score yet, with the stock's closes at both ends. */
  app.get("/api/record/inputs", ctx.guard.ingest, async (c) => {
    const today = istDay(ctx.now());
    const calls: {
      id: string;
      symbol: string;
      exchange: string;
      made_on: string;
      verdict: string;
      horizon_days: number;
    }[] = [];
    for (const [h, days] of Object.entries(WINDOW_DAYS)) {
      const cutoff = new Date(`${today}T00:00:00Z`);
      cutoff.setUTCDate(cutoff.getUTCDate() - days);
      const r = (await ctx.d1
        .prepare(
          "select c.id, c.symbol, c.exchange, c.made_on, c.verdict, c.horizon_days from calls c left join call_scores s on s.call_id = c.id where s.call_id is null and c.chance is not null and c.horizon_days = ? and c.made_on <= ? order by c.made_on limit 2000",
        )
        .bind(Number(h), cutoff.toISOString().slice(0, 10))
        .all()) as { results: typeof calls };
      calls.push(...r.results);
    }
    const watch = (
      (await ctx.d1.prepare("select id from watchlist where kind = 'stock'").all()) as {
        results: { id: string }[];
      }
    ).results.map((x) => x.id);
    const first = calls.reduce((m, x) => (m < x.made_on ? m : x.made_on), "9999");
    const closes: Record<string, [string, number][]> = {};
    if (calls.length)
      for (const s of new Set([...calls.map((x) => x.symbol), ...watch])) {
        const r = (await ctx.d1
          .prepare(
            "select date, close from stock_history where symbol = ? and date >= ? order by date",
          )
          .bind(s, first)
          .all()) as { results: { date: string; close: number }[] };
        closes[s] = r.results.map((x) => [x.date, x.close]);
      }
    return c.json({ today, calls, closes, watchlist: watch });
  });

  app.post("/api/record/scores", ctx.guard.ingest, async (c) => {
    let body: unknown;
    try {
      body = JSON.parse(rawBody(c));
    } catch {
      return c.json({ error: "bad body" }, 400);
    }
    const req = RecordRequest.safeParse(body);
    if (!req.success) return c.json({ error: "bad body" }, 400);
    let written = 0;
    for (const s of req.data.scores) {
      const res = (await ctx.d1
        .prepare(
          "insert or ignore into call_scores (call_id, beat, scored_on, stock_ret, nifty_ret, equal_ret) values (?, ?, ?, ?, ?, ?)",
        )
        .bind(s.call_id, s.beat ? 1 : 0, s.scored_on, s.stock_ret, s.nifty_ret, s.equal_ret)
        .run()) as { meta?: { changes?: number } };
      written += res.meta?.changes ?? 0;
    }
    return c.json({ written, ignored: req.data.scores.length - written });
  });

  app.get("/api/record", ctx.guard.person, async (c) => {
    const lines: TrackLine[] = [];
    for (const h of Object.keys(WINDOW_DAYS).map(Number)) {
      const t = (await ctx.d1
        .prepare(
          `select count(*) as n,
             sum(case when c.verdict = 'Buy' then 1 else 0 end) as buy_n,
             sum(case when c.verdict = 'Buy' then s.beat else 0 end) as buy_beat,
             avg((c.chance - s.beat) * (c.chance - s.beat)) as brier,
             avg((c.base_rate - s.beat) * (c.base_rate - s.beat)) as base_brier
           from calls c join call_scores s on s.call_id = c.id where c.horizon_days = ? and c.chance is not null`,
        )
        .bind(h)
        .first()) as {
        n: number;
        buy_n: number | null;
        buy_beat: number | null;
        brier: number | null;
        base_brier: number | null;
      };
      const bins = (
        (await ctx.d1
          .prepare(
            `select avg(c.chance) as said, avg(s.beat) as happened, count(*) as n from calls c join call_scores s on s.call_id = c.id
             where c.horizon_days = ? and c.chance is not null group by min(9, cast(c.chance * 10 as integer)) order by 1`,
          )
          .bind(h)
          .all()) as { results: { said: number; happened: number; n: number }[] }
      ).results;
      const buyN = t.buy_n ?? 0;
      const hit = buyN > 0 ? (t.buy_beat ?? 0) / buyN : null;
      lines.push({
        horizon_days: h,
        n: t.n,
        buy_n: buyN,
        buy_hit_rate: hit,
        brier: t.brier,
        base_brier: t.base_brier,
        calibration: bins,
        verdict: recordVerdict(t.n),
        line: trackSentence(t.n, Math.round(h / 21), hit, t.brier, t.base_brier),
      });
    }
    const v = (await ctx.d1
      .prepare(
        "select count(*) as n, avg(s.stock_ret) as stock, avg(s.nifty_ret) as nifty, avg(s.equal_ret) as equal from calls c join call_scores s on s.call_id = c.id where c.verdict = 'Buy' and s.stock_ret is not null",
      )
      .first()) as { n: number; stock: number | null; nifty: number | null; equal: number | null };
    const out: RecordResponse = { lines, value: addingValue(v.n, v.stock, v.nifty, v.equal) };
    return c.json(out);
  });

  return app;
}
