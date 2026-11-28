// Admin's one read, and Try again. Needs you, freshness per dataset, recent Job runs, Problems, usage.
import { AdminRetry, datasets } from "@stockpilot/contract";
import { Hono } from "hono";
import { type Ctx, istText } from "../app";

type Row = Record<string, string | number | null>;
const all = async (ctx: Ctx, sql: string, ...args: unknown[]): Promise<Row[]> =>
  (
    await ctx.d1
      .prepare(sql)
      .bind(...args)
      .all()
  ).results ?? [];

const hoursSince = (now: Date, at: string) => (now.getTime() - new Date(at).getTime()) / 3_600_000;

export function adminRoutes(ctx: Ctx) {
  const app = new Hono();

  app.get("/api/admin", ctx.guard.person, async (c) => {
    const now = ctx.now();
    const freshness = await Promise.all(
      Object.values(datasets).map(async (d) => {
        const [last] = await all(
          ctx,
          "select max(finished_at) as at from job_runs where kind = ? and status = 'done'",
          d.job,
        );
        const at = (last?.at as string | null) ?? null;
        const state = !at ? "never" : hoursSince(now, at) > d.freshnessHours ? "stale" : "fresh";
        return {
          dataset: d.name,
          job: d.job,
          schedule: d.schedule,
          updated_at: at,
          window_hours: d.freshnessHours,
          state,
        } as const;
      }),
    );
    const runRows = await all(
      ctx,
      "select * from job_runs order by coalesce(finished_at, started_at, queued_at) desc limit 30",
    );
    const runs = runRows.map((r) => ({
      key: String(r.key),
      kind: String(r.kind),
      day: String(r.day),
      status: r.status as "queued" | "running" | "done" | "failed",
      attempts: Number(r.attempts),
      started_at: (r.started_at as string | null) ?? null,
      finished_at: (r.finished_at as string | null) ?? null,
      error: (r.error as string | null) ?? null,
      trail: [
        r.queued_at ? { at: r.queued_at as string, text: "Queued" } : null,
        r.started_at ? { at: r.started_at as string, text: "Started" } : null,
        r.finished_at
          ? { at: r.finished_at as string, text: r.status === "failed" ? "Failed" : "Finished" }
          : null,
        r.retry_at ? { at: r.retry_at as string, text: "Will try again" } : null,
      ].filter((x): x is { at: string; text: string } => x !== null),
    }));
    const problems = (
      await all(
        ctx,
        "select id, at, message, pane, url from browser_errors order by at desc limit 50",
      )
    ).map((e) => ({
      id: String(e.id),
      at: String(e.at),
      message: String(e.message),
      pane: (e.pane as string | null) ?? null,
      url: (e.url as string | null) ?? null,
    }));
    const usage = (
      await all(
        ctx,
        "select screen, button, sum(n) as n from usage_counts group by screen, button order by n desc limit 100",
      )
    ).map((u) => ({ screen: String(u.screen), button: String(u.button), n: Number(u.n) }));

    const needs: { id: string; text: string; kind: string }[] = [];
    for (const r of runs.filter((r) => r.status === "failed"))
      needs.push({
        id: `run-${r.key}`,
        kind: "job",
        text: `${r.kind} failed on ${r.day}. Try again below.`,
      });
    for (const a of await all(ctx, "select subject from watcher_alerts where closed_at is null"))
      needs.push({ id: `alert-${a.subject}`, kind: "alert", text: `${a.subject} needs a look.` });
    for (const d of await all(ctx, "select dep, detail from dep_checks where ok = 0"))
      needs.push({ id: `dep-${d.dep}`, kind: "dependency", text: `${d.dep}: ${d.detail}` });
    for (const f of freshness.filter((f) => f.state === "stale"))
      needs.push({ id: `stale-${f.dataset}`, kind: "stale", text: `${f.dataset} is out of date.` });
    return c.json({ at: istText(now), needs_you: needs, freshness, runs, problems, usage });
  });

  // Try again: a failed Job goes back to queued; the 5-minute tick starts it.
  app.post("/api/admin/retry", ctx.guard.person, async (c) => {
    const body = AdminRetry.safeParse(await c.req.json().catch(() => undefined));
    if (!body.success) return c.json({ error: "bad body" }, 400);
    const r = await ctx.d1
      .prepare(
        "update job_runs set status = 'queued', queued_at = ?, retry_at = null, error = null, dispatched_at = null where key = ? and status = 'failed'",
      )
      .bind(istText(ctx.now()), body.data.key)
      .run();
    const changed = r?.meta?.changes ?? r?.changes ?? 0;
    if (!changed) return c.json({ error: "only a failed Job can be tried again" }, 409);
    return c.json({ key: body.data.key, status: "queued" });
  });
  return app;
}
