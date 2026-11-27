// Browser errors: the page posts what broke, one row each. A flood is cut off per day so a loop in
// a page cannot fill the store.
import { ErrorReport } from "@stockpilot/contract";
import { count, desc, like } from "drizzle-orm";
import { Hono } from "hono";
import { browserErrors } from "../../drizzle/errors";
import { type Ctx, istDay, istText } from "../app";

export const ERRORS_PER_DAY = 500;

export default function routes(ctx: Ctx) {
  const app = new Hono();
  app.post("/api/errors", ctx.guard.person, async (c) => {
    const body = ErrorReport.safeParse(await c.req.json().catch(() => undefined));
    if (!body.success) return c.json({ error: "bad report" }, 400);
    const now = ctx.now();
    const today = `${istDay(now)}%`;
    const [n] = await ctx.db
      .select({ n: count() })
      .from(browserErrors)
      .where(like(browserErrors.at, today));
    const row = { id: `err-${crypto.randomUUID()}`, at: istText(now) };
    if ((n?.n ?? 0) >= ERRORS_PER_DAY) return c.json(row);
    // Never keep a query string: a path may carry nothing private.
    const url = body.data.url?.split("?")[0]?.split("#")[0];
    await ctx.db.insert(browserErrors).values({
      ...row,
      message: body.data.message,
      stack: body.data.stack ?? null,
      pane: body.data.pane ?? null,
      url: url ?? null,
      version: body.data.version ?? null,
      userAgent: (c.req.header("user-agent") ?? "").slice(0, 200) || null,
    });
    return c.json(row);
  });
  app.get("/api/errors", ctx.guard.person, async (c) => {
    const rows = await ctx.db
      .select()
      .from(browserErrors)
      .orderBy(desc(browserErrors.at))
      .limit(50);
    return c.json({ errors: rows });
  });
  return app;
}
