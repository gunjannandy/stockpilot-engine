// The summary route: raw rows (newest holdings snapshot, trades, corporate actions, last closes) for the nightly note
// task, behind its own key. The task runs `money` on them itself; nothing here computes, and no person's sign-in opens it.
import { Hono } from "hono";
import type { Ctx } from "../app";
import { istDay } from "../app";
import { taskKey } from "./key";

// biome-ignore lint/suspicious/noExplicitAny: D1 rows are untyped; they are passed through as rows.
type Row = Record<string, any>;
const all = async (ctx: Ctx, sql: string, ...bind: unknown[]): Promise<Row[]> =>
  (
    (await ctx.d1
      .prepare(sql)
      .bind(...bind)
      .all()) as { results?: Row[] }
  ).results ?? [];

export default function routes(ctx: Ctx) {
  const app = new Hono();

  app.get("/api/summary", taskKey(ctx), async (c) => {
    const holdings = await all(
      ctx,
      `select h.account, h.source, h.snapshot_at, h.kind, h.symbol, h.isin, h.quantity, h.avg_price
       from holdings h
       join (select account, source, max(snapshot_at) as at from holdings group by account, source) m
         on m.account = h.account and m.source = h.source and m.at = h.snapshot_at
       order by h.source, h.symbol`,
    );
    const trades = await all(
      ctx,
      "select trade_key, account, source, kind, symbol, isin, side, trade_date, quantity, price from trades order by trade_date, trade_key",
    );
    const actions = await all(
      ctx,
      "select symbol, ex_date, kind, isin, numerator, denominator, subject from corporate_actions order by ex_date, symbol, kind",
    );
    const symbols = [...new Set(holdings.map((h) => h.symbol as string))].slice(0, 200);
    const closes = symbols.length
      ? await all(
          ctx,
          `select s.symbol, s.exchange, s.date, s.close from stock_history s
           join (select symbol, max(date) as d from stock_history where symbol in (${symbols.map(() => "?").join(",")}) group by symbol) m
             on m.symbol = s.symbol and m.d = s.date`,
          ...symbols,
        )
      : [];
    return c.json({ day: istDay(ctx.now()), holdings, trades, corporate_actions: actions, closes });
  });

  return app;
}
