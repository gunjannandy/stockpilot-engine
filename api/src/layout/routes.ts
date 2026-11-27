// Layout row: read by anyone signed in; written by the owner (secret header until sign-in roles land;
// the editor itself comes in ADMINCTL). The web shell falls back to the folder defaults when no row exists.
import { drizzle } from "drizzle-orm/d1";
import { Hono } from "hono";
import { z } from "zod";
import { layout } from "../../drizzle/layout";
import { type Ctx, istText } from "../app";

/** Screen ids in rail order; ids missing here follow in folder order, ids in `hidden` are not drawn. */
export const LayoutBody = z.object({
  rail: z.array(z.string().min(1).max(40)).max(40),
  hidden: z.array(z.string().min(1).max(40)).max(40).default([]),
});

export default function routes(ctx: Ctx) {
  const db = drizzle(ctx.d1);
  const app = new Hono();
  app.get("/api/layout", ctx.guard.person, async (c) => {
    const [row] = await db.select().from(layout).limit(1);
    return c.json({ layout: row ? JSON.parse(row.json) : null });
  });
  app.put("/api/layout", ctx.guard.secret, async (c) => {
    const body = LayoutBody.safeParse(await c.req.json().catch(() => undefined));
    if (!body.success) return c.json({ error: "bad body" }, 400);
    const row = { key: "default", json: JSON.stringify(body.data), updatedAt: istText(ctx.now()) };
    await db.insert(layout).values(row).onConflictDoUpdate({ target: layout.key, set: row });
    return c.json({ layout: body.data });
  });
  return app;
}
