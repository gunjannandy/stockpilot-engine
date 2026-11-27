// The ingest door (from v2's web/ingest): write-only, HMAC-signed, held to each dataset's day budget.

import {
  datasets,
  IngestRequest,
  JobFinishRequest,
  JobKind,
  JobStartRequest,
} from "@stockpilot/contract";
import { and, eq } from "drizzle-orm";
import { Hono } from "hono";
import { z } from "zod";
import { jobs, writeBudget } from "../../drizzle/core";
import { type Ctx, istDay, istText, rawBody } from "../app";

const IDENT = /^[a-z][a-z0-9_]*$/;

function json(raw: string): unknown {
  try {
    return JSON.parse(raw);
  } catch {
    return undefined;
  }
}

export default function routes(ctx: Ctx) {
  const app = new Hono();

  app.post("/api/ingest", ctx.guard.ingest, async (c) => {
    const req = IngestRequest.safeParse(json(rawBody(c)));
    if (!req.success) return c.json({ error: "bad body" }, 400);
    const ds = Object.hasOwn(datasets, req.data.dataset)
      ? (datasets as Record<string, (typeof datasets)[keyof typeof datasets]>)[req.data.dataset]
      : undefined;
    if (!ds || !(ds.row instanceof z.ZodObject) || !IDENT.test(ds.table))
      return c.json({ error: "dataset not allowed" }, 403);

    // Row checks hold a row back; the rest of the batch still goes in.
    const good = req.data.rows.flatMap((r) => {
      const p = (ds.row as z.ZodObject).safeParse(r);
      return p.success ? [p.data as Record<string, unknown>] : [];
    });
    let held = req.data.rows.length - good.length;

    const day = istDay(ctx.now());
    const [saved] = await ctx.db
      .select()
      .from(writeBudget)
      .where(and(eq(writeBudget.day, day), eq(writeBudget.dataset, ds.name)));
    const used = saved?.writes ?? 0;
    const take = good.slice(0, Math.max(0, ds.writeBudget - used));
    held += good.length - take.length;
    if (take.length === 0 && good.length > 0)
      return c.json({ error: "daily write budget reached", held_back: held }, 429);

    if (take.length > 0) {
      const cols = Object.keys((ds.row as z.ZodObject).shape);
      const insert = `insert or replace into ${ds.table} (${cols.join(",")}) values (${cols.map(() => "?").join(",")})`;
      await ctx.d1.batch([
        ...take.map((r) => ctx.d1.prepare(insert).bind(...cols.map((k) => r[k]))),
        ctx.d1
          .prepare(
            "insert into write_budget (day, dataset, writes) values (?, ?, ?) on conflict(day, dataset) do update set writes = writes + excluded.writes",
          )
          .bind(day, ds.name, take.length),
      ]);
    }
    return c.json({ accepted: take.length, held_back: held });
  });

  app.post("/api/jobs/start", ctx.guard.ingest, async (c) => {
    const req = JobStartRequest.safeParse(json(rawBody(c)));
    if (!req.success || !JobKind.safeParse(req.data.kind).success)
      return c.json({ error: "bad body" }, 400);
    const startedAt = istText(ctx.now());
    const r = await ctx.d1
      .prepare(
        "insert or ignore into jobs (id, kind, status, started_at) values (?, ?, 'running', ?)",
      )
      .bind(req.data.run_id, req.data.kind, startedAt)
      .run();
    if (r.meta.changes === 0) return c.json({ error: "run id already used" }, 409);
    return c.json({ run_id: req.data.run_id, started_at: startedAt });
  });

  app.post("/api/jobs/finish", ctx.guard.ingest, async (c) => {
    const req = JobFinishRequest.safeParse(json(rawBody(c)));
    if (!req.success) return c.json({ error: "bad body" }, 400);
    const r = await ctx.db
      .update(jobs)
      .set({
        status: req.data.status,
        result: req.data.result,
        error: req.data.error,
        finishedAt: istText(ctx.now()),
      })
      .where(and(eq(jobs.id, req.data.run_id), eq(jobs.status, "running")));
    if (r.meta.changes === 0) return c.json({ error: "no running job with that id" }, 404);
    return c.json({ ok: true });
  });

  app.get("/api/market/status", ctx.guard.ingest, (c) => {
    const date = istDay(ctx.now());
    const weekday = new Date(`${date}T00:00:00Z`).getUTCDay();
    const weekend = weekday === 0 || weekday === 6;
    return c.json({ date, is_trading_day: !weekend, reason: weekend ? "Weekend" : null });
  });

  return app;
}
