// The bench's door: the Job reads what it last scored and reports a new score. A red report pauses releases (the
// `pause_releases` flag the promote workflow reads); a green one lifts a pause only if the bench set it.
import { BenchReport, PAUSE_RELEASES } from "@stockpilot/contract";
import { Hono } from "hono";
import { type Ctx, istText, rawBody } from "../app";

const SET_BY_BENCH = "paused_releases";

type Row = { at: string; body: string };

export async function latestReport(
  ctx: Pick<Ctx, "d1">,
): Promise<(BenchReport & { at: string }) | null> {
  const r = (await ctx.d1
    .prepare("select at, body from bench_reports order by at desc limit 1")
    .first()) as Row | null;
  return r ? { ...(JSON.parse(r.body) as BenchReport), at: r.at } : null;
}

async function setPause(ctx: Ctx, enabled: boolean) {
  await ctx.d1
    .prepare("insert or replace into flags (key, enabled, updated_at) values (?, ?, ?)")
    .bind(PAUSE_RELEASES, enabled ? 1 : 0, istText(ctx.now()))
    .run();
}

export function benchRoutes(ctx: Ctx) {
  const app = new Hono();

  app.get("/api/bench/status", ctx.guard.ingest, async (c) => {
    const r = await latestReport(ctx);
    return c.json({
      fingerprint: r?.fingerprint ?? null,
      comparison: r?.comparison ?? null,
      forecast_model: r?.forecast_model ?? "haiku",
      red: r?.red ?? [],
    });
  });

  app.get("/api/bench/latest", ctx.guard.person, async (c) =>
    c.json({ report: await latestReport(ctx) }),
  );

  app.post("/api/bench/report", ctx.guard.ingest, async (c) => {
    let body: unknown;
    try {
      body = JSON.parse(rawBody(c));
    } catch {
      return c.json({ error: "bad body" }, 400);
    }
    const req = BenchReport.safeParse(body);
    if (!req.success) return c.json({ error: "bad body" }, 400);
    const at = istText(ctx.now());
    await ctx.d1
      .prepare(
        "insert or replace into bench_reports (at, fingerprint, model, red, body) values (?,?,?,?,?)",
      )
      .bind(
        at,
        req.data.fingerprint,
        req.data.model,
        JSON.stringify(req.data.red),
        JSON.stringify(req.data),
      )
      .run();
    const red = req.data.red.length > 0;
    const ours = (await ctx.d1
      .prepare("select value from bench_state where key = ?")
      .bind(SET_BY_BENCH)
      .first()) as { value: string } | null;
    if (red) {
      await setPause(ctx, true);
      await ctx.d1
        .prepare("insert or replace into bench_state (key, value) values (?, '1')")
        .bind(SET_BY_BENCH)
        .run();
    } else if (ours?.value === "1") {
      await setPause(ctx, false);
      await ctx.d1
        .prepare("insert or replace into bench_state (key, value) values (?, '0')")
        .bind(SET_BY_BENCH)
        .run();
    }
    return c.json({ ok: true, paused: red });
  });

  return app;
}
