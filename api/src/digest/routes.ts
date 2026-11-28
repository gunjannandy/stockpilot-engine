// The prototype digest: CI records a prototype that starts waiting (signed POST); the hourly Apps Script run reads
// GET /api/digest/prototypes (secret) and gets only the ones it has not been told about, so it is empty when none are new.
import { Hono } from "hono";
import { z } from "zod";
import { type Ctx, istText, rawBody } from "../app";

const Waiting = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  link: z.string().url(),
});

export default function routes(ctx: Ctx) {
  const app = new Hono();

  app.post("/api/digest/prototypes", ctx.guard.ingest, async (c) => {
    let body: unknown;
    try {
      body = JSON.parse(rawBody(c));
    } catch {
      return c.json({ error: "bad body" }, 400);
    }
    const req = Waiting.safeParse(body);
    if (!req.success) return c.json({ error: "bad body" }, 400);
    await ctx.d1
      .prepare(
        "insert or ignore into prototypes_waiting (id, title, link, waiting_since) values (?, ?, ?, ?)",
      )
      .bind(req.data.id, req.data.title, req.data.link, istText(ctx.now()))
      .run();
    return c.json({ ok: true });
  });

  app.get("/api/digest/prototypes", ctx.guard.secret, async (c) => {
    const r = (await ctx.d1
      .prepare(
        "select id, title, link, waiting_since from prototypes_waiting where announced_at is null order by waiting_since",
      )
      .all()) as { results: { id: string; title: string; link: string; waiting_since: string }[] };
    const at = istText(ctx.now());
    for (const p of r.results)
      await ctx.d1
        .prepare("update prototypes_waiting set announced_at = ? where id = ?")
        .bind(at, p.id)
        .run();
    return c.json({ prototypes: r.results });
  });

  return app;
}
