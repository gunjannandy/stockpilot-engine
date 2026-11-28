// What the private backup and drill workflows report: the latest of each, and the table counts.
// Public read (counts and names only, no row data); the write needs the ingest signature.
import { Hono } from "hono";
import { type Ctx, rawBody } from "../app";

const KINDS = ["backup", "drill"] as const;
const KEEP = 60;
type Report = { kind: string; at: string; ok: number; tables: string; detail: string };

export async function latest(ctx: Ctx) {
  const out: Record<string, unknown> = {};
  for (const kind of KINDS) {
    const row = (await ctx.d1
      .prepare(
        "select kind, at, ok, tables, detail from backup_reports where kind = ? order by at desc, id desc limit 1",
      )
      .bind(kind)
      .first()) as Report | null;
    out[kind] = row
      ? { at: row.at, ok: !!row.ok, detail: row.detail, tables: JSON.parse(row.tables) }
      : null;
  }
  return out;
}

export default function routes(ctx: Ctx) {
  const app = new Hono();
  app.get("/api/backup", async (c) => c.json(await latest(ctx)));
  app.post("/api/backup", ctx.guard.ingest, async (c) => {
    const b = JSON.parse(rawBody(c) || "null") as Record<string, unknown> | null;
    if (!b || !(KINDS as readonly string[]).includes(b.kind as string))
      return c.json({ error: "unknown kind" }, 400);
    if (typeof b.ok !== "boolean" || typeof b.detail !== "string")
      return c.json({ error: "bad body" }, 400);
    if (b.tables === null || typeof b.tables !== "object" || Array.isArray(b.tables))
      return c.json({ error: "bad tables" }, 400);
    // The report's own clock is kept for display only; ordering uses the Worker's.
    const at = ctx.now().toISOString();
    await ctx.d1
      .prepare("insert into backup_reports (kind, at, ok, tables, detail) values (?, ?, ?, ?, ?)")
      .bind(b.kind, at, b.ok ? 1 : 0, JSON.stringify(b.tables), b.detail.slice(0, 500))
      .run();
    await ctx.d1
      .prepare(
        "delete from backup_reports where kind = ? and id not in (select id from backup_reports where kind = ? order by id desc limit ?)",
      )
      .bind(b.kind, b.kind, KEEP)
      .run();
    return c.json({ ok: true });
  });
  return app;
}
