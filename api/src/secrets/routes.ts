// The secret expiry tracker: each listed secret with its expiry (a date, or null when it does not
// expire) and the days left. `due` are the ones inside the warning window not yet emailed.
import { Hono } from "hono";
import { type Ctx, istDay, istText, rawBody } from "../app";
import { SECRET_NAMES, WARN_DAYS } from "./list";

const DAY = 86400000;
const daysLeft = (today: string, on: string | null) =>
  on === null ? null : Math.round((Date.parse(on) - Date.parse(today)) / DAY);

export async function tracker(ctx: Ctx) {
  const today = istDay(ctx.now());
  const rows: { name: string; expires_on: string | null; notified_at: string | null }[] = (
    await ctx.d1.prepare("select name, expires_on, notified_at from secret_expiry").all()
  ).results;
  const by = new Map(rows.map((r) => [r.name, r]));
  const secrets = SECRET_NAMES.map((name) => {
    const r = by.get(name);
    const left = daysLeft(today, r?.expires_on ?? null);
    return {
      name,
      expires_on: r?.expires_on ?? null,
      days_left: left,
      due: left !== null && left <= WARN_DAYS && !r?.notified_at,
    };
  });
  return { today, warn_days: WARN_DAYS, secrets };
}

export default function routes(ctx: Ctx) {
  const app = new Hono();
  app.get("/api/secrets", ctx.guard.secret, async (c) => c.json(await tracker(ctx)));
  // Set or clear one secret's expiry (the date it was issued plus its lifetime), or mark it emailed.
  app.post("/api/secrets", ctx.guard.ingest, async (c) => {
    const b = JSON.parse(rawBody(c) || "null") as {
      name?: string;
      expires_on?: string | null;
      notified?: boolean;
    } | null;
    if (!b?.name || !(SECRET_NAMES as readonly string[]).includes(b.name))
      return c.json({ error: "unknown secret" }, 400);
    if (b.notified) {
      await ctx.d1
        .prepare(
          "insert into secret_expiry (name, notified_at) values (?, ?) on conflict (name) do update set notified_at = excluded.notified_at",
        )
        .bind(b.name, istText(ctx.now()))
        .run();
      return c.json({ ok: true });
    }
    if (b.expires_on != null && !/^\d{4}-\d{2}-\d{2}$/.test(b.expires_on))
      return c.json({ error: "bad date" }, 400);
    await ctx.d1
      .prepare(
        "insert into secret_expiry (name, expires_on, notified_at) values (?, ?, null) on conflict (name) do update set expires_on = excluded.expires_on, notified_at = null",
      )
      .bind(b.name, b.expires_on ?? null)
      .run();
    return c.json({ ok: true });
  });
  return app;
}
