import { datasets } from "@stockpilot/contract";
import { Hono } from "hono";
import type { Ctx } from "../app";
import { publicSourceFrom, seedPreview } from "./seed";

/** Where a preview reads production's public files (the production Worker's own address). */
const PRODUCTION = "https://stockpilotgn.pages.dev";

export default function routes(ctx: Ctx) {
  const app = new Hono();
  // The nightly reseed duty (the scheduler calls it). It exists on previews only: production answers 404.
  app.post("/api/previewseed/reseed", ctx.guard.ingest, async (c) => {
    const env = ctx.env as Record<string, string | undefined>; // SP_ENV and PRODUCTION_URL are Worker vars
    if (env.SP_ENV !== "preview") return c.json({ error: "not found" }, 404);
    const seeded = await seedPreview(ctx.d1, {
      datasets,
      publicSource: publicSourceFrom(env.PRODUCTION_URL ?? PRODUCTION),
      now: ctx.now,
    });
    return c.json({ seeded });
  });
  return app;
}
