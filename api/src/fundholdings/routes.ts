// Fund holdings for the overlap screen. Public data: the screen joins them with the person's own stocks in the
// browser (`fundOverlap` in the contract), so no holding is ever sent here.
import { type FundHoldingsRow, fundHoldings } from "@stockpilot/contract";
import { Hono } from "hono";
import type { Ctx } from "../app";

export async function loadFundHoldings(
  ctx: Pick<Ctx, "d1">,
): Promise<{ as_of: string | null; funds: FundHoldingsRow[] }> {
  const p = (await ctx.d1
    .prepare("select run_id, as_of from pointers where dataset = 'fund_holdings'")
    .first()) as { run_id: string; as_of: string } | null;
  if (!p) return { as_of: null, funds: [] };
  const r = (await ctx.d1
    .prepare(
      "select body from dataset_rows where dataset = 'fund_holdings' and run_id = ? order by seq",
    )
    .bind(p.run_id)
    .all()) as { results: { body: string }[] };
  return { as_of: p.as_of, funds: r.results.map((x) => JSON.parse(x.body) as FundHoldingsRow) };
}

export default function routes(ctx: Ctx) {
  const app = new Hono();

  // Which funds have holdings on file, without the holdings themselves.
  app.get("/api/fund-holdings", ctx.guard.person, async (c) => {
    const { as_of, funds } = await loadFundHoldings(ctx);
    return c.json({
      as_of,
      funds: funds.map(({ id, name, amc, as_of: month }) => ({ id, name, amc, as_of: month })),
    });
  });

  app.get("/api/fund-holdings/:id", ctx.guard.person, async (c) => {
    const { as_of, funds } = await loadFundHoldings(ctx);
    const f = funds.find((x) => x.id === c.req.param("id"));
    if (!f) return c.json({ error: "no holdings for this fund" }, 404);
    const { holdings_json, ...rest } = f;
    return c.json({ as_of, fund: { ...rest, holdings: fundHoldings(holdings_json) } });
  });

  return app;
}
