// GET /api/today: the day's call line (one money function, shared with the email), money left, market health, and the
// held and watched stocks grouped by their call. Money left and the portfolio are not headline items: they ride along.
import type { TodayResponse } from "@stockpilot/contract";
import { Hono } from "hono";
import { callLine } from "../../../money/src/callline/callline";
import { type Ctx, istDay, istText } from "../app";
import { currentPointer } from "../publish/lib";

type CallRow = { symbol: string; verdict: string; chance: number | null; made_on: string };

const GROUP: Record<string, keyof TodayResponse["groups"]> = {
  Sell: "sell",
  Weak: "weak",
  Hold: "fine_keep",
  Watch: "close_to_buy",
};

export default function routes(ctx: Ctx) {
  const app = new Hono();

  app.get("/api/today", ctx.guard.person, async (c) => {
    const day = istDay(ctx.now());
    const calls = (
      (await ctx.d1
        .prepare(
          "select c.symbol, c.verdict, c.chance, c.made_on from calls c join (select exchange, symbol, max(made_on) as m from calls group by exchange, symbol) l on l.exchange = c.exchange and l.symbol = c.symbol and l.m = c.made_on where c.horizon_days = 63",
        )
        .all()) as { results: CallRow[] }
    ).results;
    const held = new Set(
      (
        (await ctx.d1
          .prepare(
            `select distinct h.symbol from holdings h join (select account, source, max(snapshot_at) as at from holdings group by account, source) m on m.account = h.account and m.source = h.source and m.at = h.snapshot_at where h.kind = 'stock'`,
          )
          .all()) as { results: { symbol: string }[] }
      ).results.map((x) => x.symbol),
    );
    const watched = new Set(
      (
        (await ctx.d1.prepare("select id from watchlist where kind = 'stock'").all()) as {
          results: { id: string }[];
        }
      ).results.map((x) => x.id),
    );
    const hidden = new Set(
      (
        (await ctx.d1
          .prepare("select symbol from not_now where until > ?")
          .bind(istText(ctx.now()))
          .all()) as { results: { symbol: string }[] }
      ).results.map((x) => x.symbol),
    );
    const budget = (await ctx.d1
      .prepare("select amount_inr from money_budgets where month = ?")
      .bind(day.slice(0, 7))
      .first()) as { amount_inr: number } | null;
    const spent = (await ctx.d1
      .prepare(
        "select coalesce(sum(quantity * price), 0) as s from trades where side = 'buy' and kind = 'stock' and substr(trade_date, 1, 7) = ?",
      )
      .bind(day.slice(0, 7))
      .first()) as { s: number } | null;
    const moneyLeft = budget ? budget.amount_inr - (spent?.s ?? 0) : null;

    const line = callLine({
      calls: calls.map((x) => ({
        symbol: x.symbol,
        verdict: x.verdict,
        chance: x.chance,
        madeOn: x.made_on,
      })),
      held,
      moneyLeft,
      notNow: hidden,
    });
    const groups: TodayResponse["groups"] = {
      sell: [],
      weak: [],
      fine_keep: [],
      close_to_buy: [],
      unusual: [],
    };
    for (const x of calls) {
      const g = GROUP[x.verdict];
      if (g && (held.has(x.symbol) || watched.has(x.symbol)) && !hidden.has(x.symbol))
        groups[g].push(x.symbol);
    }
    for (const g of Object.values(groups)) g.sort();

    const m = await currentPointer(ctx, "market");
    const mrow = m
      ? ((await ctx.d1
          .prepare(
            "select body from dataset_rows where dataset = 'market' and run_id = ? order by seq limit 1",
          )
          .bind(m.runId)
          .first()) as { body: string } | null)
      : null;
    const parsed = mrow ? (JSON.parse(mrow.body) as Record<string, unknown>) : null;
    const asOf = calls.reduce<string | null>((a, x) => (a && a > x.made_on ? a : x.made_on), null);
    const out = {
      call_line: line,
      money_left_inr: moneyLeft,
      market: parsed
        ? {
            ...parsed,
            sentences: JSON.parse(String(parsed.sentences_json)),
            sentences_json: undefined,
          }
        : null,
      groups,
      as_of: asOf,
      stale_held: [...held]
        .filter((s) => !calls.some((x) => x.symbol === s && asOf && x.made_on >= asOf))
        .sort(),
    } as TodayResponse;
    return c.json(out);
  });

  return app;
}
