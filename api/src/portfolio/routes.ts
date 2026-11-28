// PORTFOLIO's backend: raw holdings, trades and corporate actions behind sign-in (the browser computes with
// `money`), and the owner's budget and target mix. Reads only from the broker's stored rows; no broker call.
import {
  ActionsResponse,
  BudgetBody,
  HoldingsResponse,
  MixBody,
  TradesResponse,
} from "@stockpilot/contract";
import { Hono } from "hono";
import { type Ctx, istText } from "../app";
import { ownerOnly } from "../auth/lib";

// biome-ignore lint/suspicious/noExplicitAny: D1 rows are untyped; each column is read once, below.
type Row = Record<string, any>;
const all = async (ctx: Ctx, sql: string): Promise<Row[]> =>
  ((await ctx.d1.prepare(sql).all()) as { results?: Row[] }).results ?? [];

export default function routes(ctx: Ctx) {
  const app = new Hono();

  // The newest snapshot of each source, so a new Kite sync shows at once with no Job (C-059-2).
  app.get("/api/portfolio/holdings", ctx.guard.person, async (c) => {
    const rows = await all(
      ctx,
      `select h.account, h.source, h.snapshot_at, h.kind, h.symbol, h.isin, h.quantity, h.avg_price
       from holdings h
       join (select account, source, max(snapshot_at) as at from holdings group by account, source) m
         on m.account = h.account and m.source = h.source and m.at = h.snapshot_at
       order by h.source, h.symbol`,
    );
    return c.json(
      HoldingsResponse.parse({ holdings: rows.map((r) => ({ ...r, isin: r.isin ?? null })) }),
    );
  });

  app.get("/api/portfolio/trades", ctx.guard.person, async (c) => {
    const rows = await all(
      ctx,
      "select trade_key, account, source, source_ref, kind, symbol, isin, side, trade_date, quantity, price from trades order by trade_date, trade_key",
    );
    return c.json(
      TradesResponse.parse({
        trades: rows.map((r) => ({ ...r, isin: r.isin ?? null, price: r.price ?? null })),
      }),
    );
  });

  app.get("/api/portfolio/corporate-actions", ctx.guard.person, async (c) => {
    const rows = await all(
      ctx,
      `select a.symbol, a.ex_date, a.kind, a.isin, a.numerator, a.denominator, a.subject, a.source,
              t.symbol as t_symbol, t.new_isin, t.new_symbol, t.cost_fraction, t.price
       from corporate_actions a
       left join action_terms t on t.symbol = a.symbol and t.ex_date = a.ex_date and t.kind = a.kind
       order by a.ex_date, a.symbol, a.kind`,
    );
    const actions = rows.map((r) => ({
      symbol: r.symbol,
      ex_date: r.ex_date,
      kind: r.kind,
      isin: r.isin ?? null,
      numerator: r.numerator,
      denominator: r.denominator,
      subject: r.subject,
      source: r.source,
      terms: r.t_symbol
        ? {
            new_isin: r.new_isin ?? null,
            new_symbol: r.new_symbol ?? null,
            cost_fraction: r.cost_fraction ?? null,
            price: r.price ?? null,
          }
        : null,
    }));
    return c.json(ActionsResponse.parse({ actions }));
  });

  // Budget and mix are the owner's alone, to read and to write (C-057-1): the father gets 403.
  app.get("/api/portfolio/settings", ownerOnly(ctx), async (c) => {
    const b = await all(ctx, "select month, amount_inr from money_budgets order by month");
    const m = await all(ctx, "select asset_class, share from money_mix order by asset_class");
    const def = b.find((r) => r.month === "default");
    return c.json({
      budget: def
        ? {
            default: def.amount_inr,
            months: Object.fromEntries(
              b.filter((r) => r.month !== "default").map((r) => [r.month, r.amount_inr]),
            ),
          }
        : null,
      mix: m.length ? Object.fromEntries(m.map((r) => [r.asset_class, r.share])) : null,
    });
  });
  // A write replaces the whole setting, in one batch, so a half-saved budget or mix cannot be read.
  app.put("/api/portfolio/budget", ownerOnly(ctx), async (c) => {
    const body = BudgetBody.safeParse(await c.req.json().catch(() => undefined));
    if (!body.success) return c.json({ error: "bad body" }, 400);
    const at = istText(ctx.now());
    const put = "insert into money_budgets (month, amount_inr, updated_at) values (?, ?, ?)";
    await ctx.d1.batch([
      ctx.d1.prepare("delete from money_budgets"),
      ctx.d1.prepare(put).bind("default", body.data.default, at),
      ...Object.entries(body.data.months).map(([m, v]) => ctx.d1.prepare(put).bind(m, v, at)),
    ]);
    return c.json({ budget: body.data });
  });
  app.put("/api/portfolio/mix", ownerOnly(ctx), async (c) => {
    const body = MixBody.safeParse(await c.req.json().catch(() => undefined));
    if (!body.success) return c.json({ error: "bad body" }, 400);
    const at = istText(ctx.now());
    await ctx.d1.batch([
      ctx.d1.prepare("delete from money_mix"),
      ...Object.entries(body.data.mix).map(([k, v]) =>
        ctx.d1
          .prepare("insert into money_mix (asset_class, share, updated_at) values (?, ?, ?)")
          .bind(k, v, at),
      ),
    ]);
    return c.json(body.data);
  });
  return app;
}
