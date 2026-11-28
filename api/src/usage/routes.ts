// A click writes one count (story 107). Counts only: no user, no content.
import { UsageHit } from "@stockpilot/contract";
import { Hono } from "hono";
import { adminRoutes } from "../admin/overview";
import { type Ctx, istDay } from "../app";

export default function routes(ctx: Ctx) {
  const app = new Hono();
  app.post("/api/usage", ctx.guard.person, async (c) => {
    const hit = UsageHit.safeParse(await c.req.json().catch(() => undefined));
    if (!hit.success) return c.json({ error: "bad body" }, 400);
    await ctx.d1
      .prepare(
        "insert into usage_counts (day, screen, button, n) values (?, ?, ?, 1) on conflict (day, screen, button) do update set n = n + 1",
      )
      .bind(istDay(ctx.now()), hit.data.screen, hit.data.button ?? "")
      .run();
    return c.json({ ok: true });
  });
  // Admin's read and Try again ride in this area: a folder named admin would sort ahead of auth.
  app.route("/", adminRoutes(ctx));
  return app;
}
