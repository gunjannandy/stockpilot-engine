import { FlagWrite } from "@stockpilot/contract";
import { Hono } from "hono";
import { flags } from "../../drizzle/core";
import { type Ctx, istText } from "../app";

export default function routes(ctx: Ctx) {
  const app = new Hono();
  app.get("/api/flags", ctx.guard.person, async (c) => {
    const rows = await ctx.db.select().from(flags);
    return c.json({ flags: Object.fromEntries(rows.map((r) => [r.key, r.enabled])) });
  });
  // The owner's write. Until sign-in lands it is behind the same secret header as health.
  app.post("/api/flags", ctx.guard.secret, async (c) => {
    const req = FlagWrite.safeParse(await c.req.json().catch(() => undefined));
    if (!req.success) return c.json({ error: "bad body" }, 400);
    const row = { key: req.data.key, enabled: req.data.enabled, updatedAt: istText(ctx.now()) };
    await ctx.db.insert(flags).values(row).onConflictDoUpdate({ target: flags.key, set: row });
    return c.json({ key: row.key, enabled: row.enabled });
  });
  return app;
}
