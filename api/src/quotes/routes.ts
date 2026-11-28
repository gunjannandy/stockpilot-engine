import { QUOTE_MAX_AGE_SECONDS } from "@stockpilot/contract";
import { Hono } from "hono";
import type { Ctx } from "../app";
import { readQuote, watch } from "./quotes";

export default function routes(ctx: Ctx) {
  const app = new Hono();
  // Answers from the cache only; a symbol with nothing fresh is listed in `stale`, never fetched here.
  app.get("/api/quotes", ctx.guard.person, async (c) => {
    const symbols = (c.req.query("symbols") ?? "")
      .split(",")
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean)
      .slice(0, 100);
    const quotes = [];
    const stale: string[] = [];
    for (const s of symbols) {
      await watch(ctx, s);
      const q = await readQuote(ctx, s);
      if (q) quotes.push(q);
      else stale.push(s);
    }
    c.header("cache-control", "private, max-age=30");
    return c.json({ quotes, stale, max_age_seconds: QUOTE_MAX_AGE_SECONDS });
  });
  return app;
}
