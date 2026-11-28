// The ingest door (from v2's web/ingest): write-only, HMAC-signed, held to each dataset's day budget.

import { datasets, IngestRequest, migrationDatasets } from "@stockpilot/contract";
import { and, eq } from "drizzle-orm";
import { Hono } from "hono";
import { z } from "zod";
import { writeBudget } from "../../drizzle/core";
import { type Ctx, istDay, rawBody } from "../app";

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
    // The one-time v2 copy's tables: checked, no day budget, replaced by key so a rerun changes nothing.
    const mig = Object.hasOwn(migrationDatasets, req.data.dataset)
      ? (
          migrationDatasets as Record<
            string,
            (typeof migrationDatasets)[keyof typeof migrationDatasets]
          >
        )[req.data.dataset]
      : undefined;
    if (mig) {
      const keep = req.data.rows.flatMap((r) => {
        const p = mig.row.safeParse(r);
        return p.success ? [p.data as Record<string, unknown>] : [];
      });
      const cols = Object.keys(mig.row.shape);
      const del = `delete from ${mig.table} where ${mig.keys.map((k) => `${k} is ?`).join(" and ")}`;
      const ins = `insert into ${mig.table} (${cols.join(",")}) values (${cols.map(() => "?").join(",")})`;
      for (let i = 0; i < keep.length; i += 40)
        await ctx.d1.batch(
          keep
            .slice(i, i + 40)
            .flatMap((r) => [
              ctx.d1.prepare(del).bind(...mig.keys.map((k) => r[k])),
              ctx.d1.prepare(ins).bind(...cols.map((k) => r[k])),
            ]),
        );
      return c.json({ accepted: keep.length, held_back: req.data.rows.length - keep.length });
    }
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

  return app;
}
