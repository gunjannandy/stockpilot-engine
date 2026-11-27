import { count, desc } from "drizzle-orm";
import { Hono } from "hono";
import { ping } from "../../drizzle/core";
import { type Ctx, istText } from "../app";

export default function routes(ctx: Ctx) {
  const app = new Hono();
  app.post("/api/ping", ctx.guard.person, async (c) => {
    const row = {
      id: `button-${crypto.randomUUID()}`,
      at: istText(ctx.now()),
      source: "button" as const,
    };
    await ctx.db.insert(ping).values(row);
    return c.json(row);
  });
  app.get("/api/ping", ctx.guard.person, async (c) => {
    const [latest] = await ctx.db
      .select()
      .from(ping)
      .orderBy(desc(ping.at), desc(ping.id))
      .limit(1);
    const [n] = await ctx.db.select({ n: count() }).from(ping);
    return c.json({ latest: latest ?? null, count: n?.n ?? 0 });
  });
  return app;
}
