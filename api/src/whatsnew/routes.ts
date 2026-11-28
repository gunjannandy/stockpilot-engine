// What's new, once per person. promote.yml posts the lines to POST /api/whatsnew; this area stores them,
// answers which a person has not seen yet, and records that they have.
import { WhatsNewPost } from "@stockpilot/contract";
import { desc, eq } from "drizzle-orm";
import { drizzle } from "drizzle-orm/d1";
import { Hono } from "hono";
import { z } from "zod";
import { whatsnew, whatsnewSeen } from "../../drizzle/whatsnew";
import { type Ctx, istText, rawBody } from "../app";

const Seen = z.object({ pr: z.number().int().positive() });

export default function routes(ctx: Ctx) {
  const db = drizzle(ctx.d1);
  const app = new Hono();
  // Dev mode (tests) lets everyone in as the owner without setting a person.
  const who = (c: unknown) =>
    (c as { get(k: string): string | undefined }).get("person") ?? "owner";

  app.post("/api/whatsnew", ctx.guard.ingest, async (c) => {
    const req = WhatsNewPost.safeParse(JSON.parse(rawBody(c) || "null"));
    if (!req.success) return c.json({ error: "bad body" }, 400);
    const at = istText(ctx.now());
    for (const l of req.data.lines)
      await db
        .insert(whatsnew)
        .values({ ...l, at })
        .onConflictDoUpdate({ target: whatsnew.pr, set: { en: l.en, bn: l.bn, at } });
    return c.json({ stored: req.data.lines.length });
  });
  app.get("/api/whatsnew", ctx.guard.person, async (c) => {
    const rows = await db.select().from(whatsnew).orderBy(desc(whatsnew.at), desc(whatsnew.pr));
    return c.json({ lines: rows });
  });

  app.get("/api/whatsnew/unseen", ctx.guard.person, async (c) => {
    const done = new Set(
      (
        await db
          .select({ pr: whatsnewSeen.pr })
          .from(whatsnewSeen)
          .where(eq(whatsnewSeen.person, who(c)))
      ).map((r) => r.pr),
    );
    const rows = (await db.select().from(whatsnew)).filter((r) => !done.has(r.pr));
    return c.json({
      lines: rows.sort((a, b) => a.pr - b.pr).map(({ pr, en, bn }) => ({ pr, en, bn })),
    });
  });

  app.post("/api/whatsnew/seen", ctx.guard.person, async (c) => {
    const body = Seen.safeParse(await c.req.json().catch(() => undefined));
    if (!body.success) return c.json({ error: "bad body" }, 400);
    await db
      .insert(whatsnewSeen)
      .values({ person: who(c), pr: body.data.pr, at: istText(ctx.now()) })
      .onConflictDoNothing();
    return c.json({ ok: true });
  });
  return app;
}
