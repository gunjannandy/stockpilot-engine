// GET /api/market/indices: a stub that answers the contract's shape with nothing in it, so Market and news
// can be wired against a real route. The index dataset replaces the empty list when it lands.
import type { IndicesResponse } from "@stockpilot/contract";
import { Hono } from "hono";
import type { Ctx } from "../app";

export default function routes(ctx: Ctx) {
  const app = new Hono();
  app.get("/api/market/indices", ctx.guard.person, (c) =>
    c.json({ as_of: null, indices: [] } satisfies IndicesResponse),
  );
  return app;
}
