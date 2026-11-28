// The weekly fund calls (buy, watch) and their track record, from public NAV history. Held funds are matched
// privately elsewhere; nothing here knows what anyone holds.
import type { FundCallRow } from "@stockpilot/contract";
import { Hono } from "hono";
import type { Ctx } from "../app";

export async function loadFundCalls(
  ctx: Pick<Ctx, "d1">,
): Promise<{ as_of: string | null; rows: FundCallRow[] }> {
  const p = (await ctx.d1
    .prepare("select run_id, as_of from pointers where dataset = 'fund_calls'")
    .first()) as { run_id: string; as_of: string } | null;
  if (!p) return { as_of: null, rows: [] };
  const r = (await ctx.d1
    .prepare(
      "select body from dataset_rows where dataset = 'fund_calls' and run_id = ? order by seq",
    )
    .bind(p.run_id)
    .all()) as { results: { body: string }[] };
  return { as_of: p.as_of, rows: r.results.map((x) => JSON.parse(x.body) as FundCallRow) };
}

export default function routes(ctx: Ctx) {
  const app = new Hono();

  // GET /api/fund-calls gives { as_of, calls, track }: calls best rank first, track record by kind and quartile.
  app.get("/api/fund-calls", ctx.guard.person, async (c) => {
    const { as_of, rows } = await loadFundCalls(ctx);
    const calls = rows
      .filter((r) => r.kind === "call")
      .sort(
        (a, b) =>
          (a.call === b.call ? 0 : a.call === "buy" ? -1 : 1) || (a.rank ?? 0) - (b.rank ?? 0),
      );
    const track = rows.filter((r) => r.kind === "track");
    return c.json({ as_of, calls, track });
  });

  return app;
}
