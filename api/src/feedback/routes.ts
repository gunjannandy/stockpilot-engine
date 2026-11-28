import { FeedbackPost, FeedbackReview } from "@stockpilot/contract";
import { desc, eq } from "drizzle-orm";
import { Hono } from "hono";
import { type GithubBot, githubFromEnv } from "../../../adapters/src/github";
import { feedback } from "../../drizzle/feedback";
import { type Ctx, istText } from "../app";
import { authEnv, devMode, ownerOnly, sessionPerson } from "../auth/lib";
import { openTicket } from "./feedback";

type Row = typeof feedback.$inferSelect;
const shape = (r: Row) => ({
  id: r.id,
  text: r.text,
  understanding: r.understanding,
  status: r.status,
  job: r.ticket,
  created_at: r.createdAt,
});

export function feedbackRoutes(ctx: Ctx, botOf: () => GithubBot | undefined) {
  const app = new Hono();
  app.get("/api/feedback", ctx.guard.person, async (c) => {
    const person =
      devMode(authEnv(ctx)) || (await sessionPerson(ctx, c.req.raw)) === "owner"
        ? "owner"
        : "father";
    const rows = await ctx.db.select().from(feedback).orderBy(desc(feedback.createdAt)).limit(200);
    return c.json({
      asks: rows.map(shape),
      person,
      updated_at:
        rows
          .map((r) => r.updatedAt)
          .sort()
          .at(-1) ?? null,
    });
  });
  app.post("/api/feedback", ctx.guard.person, async (c) => {
    const body = FeedbackPost.safeParse(await c.req.json().catch(() => undefined));
    if (!body.success) return c.json({ error: "bad body" }, 400);
    const at = istText(ctx.now());
    const row = {
      id: `fb-${crypto.randomUUID()}`,
      text: body.data.text,
      status: "received",
      createdAt: at,
      updatedAt: at,
    };
    await ctx.db.insert(feedback).values(row);
    return c.json(
      shape({ ...row, understanding: null, ticket: null, staleTicket: null, reviewedAt: null }),
    );
  });
  // Only the owner decides. The ticket is opened here by code; if the bot is down the ask stays
  // Reviewed and the next pass (followTickets' caller) opens it.
  app.post("/api/feedback/:id/review", ownerOnly(ctx), async (c) => {
    const body = FeedbackReview.safeParse(await c.req.json().catch(() => undefined));
    if (!body.success) return c.json({ error: "bad body" }, 400);
    const id = c.req.param("id") as string;
    const [row] = await ctx.db.select().from(feedback).where(eq(feedback.id, id)).limit(1);
    if (!row) return c.json({ error: "not found" }, 404);
    const at = istText(ctx.now());
    await ctx.db
      .update(feedback)
      .set({
        understanding: body.data.understanding,
        status: body.data.decision,
        reviewedAt: at,
        updatedAt: at,
      })
      .where(eq(feedback.id, id));
    if (body.data.decision === "reviewed") {
      const bot = botOf();
      if (bot) await openTicket(ctx, bot, id).catch(() => null);
    }
    const [fresh] = await ctx.db.select().from(feedback).where(eq(feedback.id, id)).limit(1);
    return c.json(shape(fresh as Row));
  });
  return app;
}

export default function routes(ctx: Ctx) {
  return feedbackRoutes(ctx, () => githubFromEnv(ctx.env as Record<string, string | undefined>));
}
