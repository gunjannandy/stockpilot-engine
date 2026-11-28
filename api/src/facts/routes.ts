// GET /api/facts/:symbol: one stock's facts (metrics, sector comparison, plain sentences in both languages and the
// raw figures table). Reads the current run of the public `facts` dataset; a stock with none answers facts: null.
import {
  type FactsResponse,
  type FactsRow,
  factFigures,
  factSentences,
} from "@stockpilot/contract";
import { Hono } from "hono";
import type { Ctx } from "../app";

export default function routes(ctx: Ctx) {
  const app = new Hono();

  app.get("/api/facts/:symbol", ctx.guard.person, async (c) => {
    const symbol = c.req.param("symbol").toUpperCase();
    const p = (await ctx.d1
      .prepare("select run_id, as_of from pointers where dataset = 'facts'")
      .first()) as { run_id: string; as_of: string } | null;
    const empty: FactsResponse = { as_of: p?.as_of ?? null, facts: null };
    if (!p) return c.json(empty);
    const r = (await ctx.d1
      .prepare(
        "select body from dataset_rows where dataset = 'facts' and run_id = ? and json_extract(body, '$.symbol') = ? order by seq limit 1",
      )
      .bind(p.run_id, symbol)
      .first()) as { body: string } | null;
    if (!r) return c.json(empty);
    const row = JSON.parse(r.body) as FactsRow;
    const { sentences_json, figures_json, ...rest } = row;
    const out: FactsResponse = {
      as_of: p.as_of,
      facts: {
        ...rest,
        sentences: factSentences(sentences_json),
        figures: factFigures(figures_json),
      },
    };
    return c.json(out);
  });

  return app;
}
