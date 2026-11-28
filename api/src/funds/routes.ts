// The funds routes the Funds screen reads: a searchable list and one fund with its NAV history.
// Rows are the `funds` dataset's current run (posted by the funds Job).
import { type FundRow, type FundSummary, fundNavs } from "@stockpilot/contract";
import { Hono } from "hono";
import type { Ctx } from "../app";

const LIST_LIMIT = 50;

/** The current funds: the rows of the `funds` dataset's current run, or none. */
export async function loadFunds(
  ctx: Pick<Ctx, "d1">,
): Promise<{ as_of: string | null; funds: FundRow[] }> {
  const p = (await ctx.d1
    .prepare("select run_id, as_of from pointers where dataset = 'funds'")
    .first()) as { run_id: string; as_of: string } | null;
  if (!p) return { as_of: null, funds: [] };
  const r = (await ctx.d1
    .prepare("select body from dataset_rows where dataset = 'funds' and run_id = ? order by seq")
    .bind(p.run_id)
    .all()) as { results: { body: string }[] };
  return { as_of: p.as_of, funds: r.results.map((x) => JSON.parse(x.body) as FundRow) };
}

export function summary(f: FundRow): FundSummary {
  const { navs_json: _navs, ...rest } = f;
  return rest;
}

/** Every word asked for must appear in the fund's name, house or category. */
export function matches(f: FundRow, q: string): boolean {
  const hay = `${f.name} ${f.amc ?? ""} ${f.category ?? ""}`.toLowerCase();
  return q
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((w) => hay.includes(w));
}

export default function routes(ctx: Ctx) {
  const app = new Hono();

  // ?q= words, ?category= exact, ?limit= (default 50). Sorted by name; `total` counts all matches.
  app.get("/api/funds", ctx.guard.person, async (c) => {
    const { as_of, funds } = await loadFunds(ctx);
    const q = c.req.query("q") ?? "";
    const category = c.req.query("category");
    const asked = Number(c.req.query("limit"));
    const limit = Number.isInteger(asked) && asked > 0 ? Math.min(asked, 500) : LIST_LIMIT;
    const hits = funds
      .filter((f) => (category ? f.category === category : true) && matches(f, q))
      .sort((a, b) => a.name.localeCompare(b.name));
    const categories = [...new Set(funds.map((f) => f.category).filter((x) => x))].sort();
    return c.json({
      as_of,
      total: hits.length,
      categories,
      funds: hits.slice(0, limit).map(summary),
    });
  });

  app.get("/api/funds/:id", ctx.guard.person, async (c) => {
    const { as_of, funds } = await loadFunds(ctx);
    const fund = funds.find((f) => f.id === c.req.param("id"));
    if (!fund) return c.json({ error: "no such fund" }, 404);
    const { navs_json, ...rest } = fund;
    return c.json({ as_of, fund: { ...rest, navs: fundNavs(navs_json) } });
  });

  return app;
}
