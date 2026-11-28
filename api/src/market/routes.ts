// GET /api/market/indices: the Nifty from the newest `market` row (the market health Job's one row a day).
// The dataset holds the close and the trend against the 200-day average, not a one-day change, so the day's
// change is null rather than guessed. With no run published yet the answer is empty, which the pane says.
import type { IndicesResponse } from "@stockpilot/contract";
import { Hono } from "hono";
import type { Ctx } from "../app";
import { currentPointer } from "../publish/lib";

type MarketRow = { day?: unknown; nifty_close?: unknown };

export default function routes(ctx: Ctx) {
  const app = new Hono();
  app.get("/api/market/indices", ctx.guard.person, async (c) => {
    const empty: IndicesResponse = { as_of: null, indices: [] };
    const p = await currentPointer(ctx, "market");
    if (!p) return c.json(empty);
    const r = (await ctx.d1
      .prepare(
        "select body from dataset_rows where dataset = 'market' and run_id = ? order by seq desc limit 1",
      )
      .bind(p.runId)
      .first()) as { body: string } | null;
    if (!r) return c.json(empty);
    let row: MarketRow;
    try {
      row = JSON.parse(r.body) as MarketRow;
    } catch {
      return c.json(empty);
    }
    const day = typeof row.day === "string" && /^\d{4}-\d{2}-\d{2}$/.test(row.day) ? row.day : null;
    const close = typeof row.nifty_close === "number" ? row.nifty_close : null;
    if (!day || close === null) return c.json(empty);
    return c.json({
      as_of: `${day}T15:30:00+05:30`,
      indices: [{ id: "nifty50", name: "Nifty 50", close, change_pct: null }],
    } satisfies IndicesResponse);
  });
  return app;
}
