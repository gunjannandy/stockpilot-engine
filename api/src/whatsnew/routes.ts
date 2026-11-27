// What's new, once per person. promote.yml posts the lines to health's POST /api/whatsnew; this area
// answers which of them a person has not seen yet, and records that they have.
import { eq } from "drizzle-orm";
import { drizzle } from "drizzle-orm/d1";
import { Hono } from "hono";
import { z } from "zod";
import { whatsnew } from "../../drizzle/core";
import { whatsnewSeen } from "../../drizzle/whatsnew";
import { type Ctx, istText } from "../app";

const Seen = z.object({ pr: z.number().int().positive() });

export default function routes(ctx: Ctx) {
  const db = drizzle(ctx.d1);
  const app = new Hono();
  // Dev mode (tests) lets everyone in as the owner without setting a person.
  const who = (c: unknown) =>
    (c as { get(k: string): string | undefined }).get("person") ?? "owner";

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
