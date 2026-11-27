// The check runner: runs every production check and stores each result (story 159).
import { Hono } from "hono";
import { checkResults } from "../../drizzle/core";
import { type Ctx, istText, type ProductionCheck } from "../app";

const NEXT_BEAT_MS = 3 * 24 * 3600 * 1000;

export async function runChecks(ctx: Ctx) {
  const all = ctx.registry.areas.flatMap((a) => a.checks ?? []);
  const ordered: ProductionCheck[] = [...all.filter((k) => !k.last), ...all.filter((k) => k.last)];
  const run = { startedAt: istText(ctx.now()) };
  const results: { id: string; ok: boolean; detail: string }[] = [];
  for (const check of ordered) {
    let out: { ok: boolean; detail: string };
    try {
      out = await check.run(ctx, run);
    } catch (err) {
      out = {
        ok: false,
        detail: `check crashed: ${err instanceof Error ? err.message : String(err)}`,
      };
    }
    const row = {
      checkId: check.id,
      ok: out.ok,
      at: istText(ctx.now()),
      detail: out.detail.slice(0, 300),
    };
    await ctx.db
      .insert(checkResults)
      .values(row)
      .onConflictDoUpdate({ target: checkResults.checkId, set: row });
    results.push({ id: check.id, ...out });
  }
  const at = istText(ctx.now());
  const ok = results.every((r) => r.ok);
  await ctx.d1
    .prepare(
      "insert into heartbeats (part, version, at, ok, error, next_expected_by, last_success) values ('check_runner', ?, ?, ?, ?, ?, ?) " +
        "on conflict(part) do update set version = excluded.version, at = excluded.at, ok = excluded.ok, error = excluded.error, " +
        "next_expected_by = excluded.next_expected_by, last_success = coalesce(excluded.last_success, last_success)",
    )
    .bind(
      ctx.version,
      at,
      ok ? 1 : 0,
      ok
        ? null
        : results
            .filter((r) => !r.ok)
            .map((r) => r.id)
            .join(", "),
      istText(new Date(ctx.now().getTime() + NEXT_BEAT_MS)),
      ok ? at : null,
    )
    .run();
  return results;
}

export default function routes(ctx: Ctx) {
  const app = new Hono();
  app.post("/api/checks/run", ctx.guard.ingest, async (c) =>
    c.json({ results: await runChecks(ctx) }),
  );
  return app;
}
