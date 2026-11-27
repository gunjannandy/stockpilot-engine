// The budget monitor: D1 size is measured here; reads, writes, Worker requests and Workers Builds
// minutes are reported by the scheduler (it holds the Cloudflare read access). Public, no data:
// the dispatchers read it on /api/monitor to pace themselves.
import { Hono } from "hono";
import { type Ctx, istDay, istText, rawBody } from "../app";

export const METRICS = ["d1_reads", "d1_writes", "worker_requests", "build_minutes"] as const;

export async function d1Bytes(ctx: Ctx): Promise<number> {
  // The pragma table functions work in SQLite but D1 may refuse them; D1 reports the size on
  // every query result (meta.size_after), so fall back to that rather than answering 500.
  try {
    const row = await ctx.d1
      .prepare(
        "select (select page_count from pragma_page_count()) * (select page_size from pragma_page_size()) as bytes",
      )
      .first();
    const bytes = Number(row?.bytes ?? 0);
    if (bytes > 0) return bytes;
  } catch {
    // fall through to the D1 meta size
  }
  try {
    const r = await ctx.d1.prepare("select 1").all();
    return Number(r?.meta?.size_after ?? 0);
  } catch {
    return 0;
  }
}

export async function usageToday(ctx: Ctx) {
  const day = istDay(ctx.now());
  const rows: { metric: string; value: number; at: string }[] = (
    await ctx.d1
      .prepare("select metric, value, at from monitor_usage where day = ?")
      .bind(day)
      .all()
  ).results;
  const got = new Map(rows.map((r) => [r.metric, r]));
  return {
    day,
    d1_bytes: await d1Bytes(ctx),
    ...Object.fromEntries(METRICS.map((m) => [m, got.get(m)?.value ?? 0])),
    reported_at:
      rows
        .map((r) => r.at)
        .sort()
        .at(-1) ?? null,
  };
}

export default function routes(ctx: Ctx) {
  const app = new Hono();
  app.get("/api/monitor", async (c) => c.json(await usageToday(ctx)));
  app.post("/api/monitor", ctx.guard.ingest, async (c) => {
    const body = JSON.parse(rawBody(c) || "null") as Record<string, unknown> | null;
    if (!body || typeof body !== "object") return c.json({ error: "bad body" }, 400);
    const day = istDay(ctx.now());
    const at = istText(ctx.now());
    let stored = 0;
    for (const m of METRICS) {
      const v = body[m];
      if (typeof v !== "number" || !Number.isFinite(v) || v < 0) continue;
      await ctx.d1
        .prepare(
          "insert into monitor_usage (day, metric, value, at) values (?, ?, ?, ?) on conflict (day, metric) do update set value = excluded.value, at = excluded.at",
        )
        .bind(day, m, v, at)
        .run();
      stored++;
    }
    return c.json({ stored });
  });
  return app;
}
