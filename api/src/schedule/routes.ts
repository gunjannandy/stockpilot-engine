// A button Job (Analyse, load a stock, Refresh, Recompute) is dispatched the moment it is pressed.
import { JobPressRequest } from "@stockpilot/contract";
import { Hono } from "hono";
import { type GithubBot, githubFromEnv } from "../../../adapters/src/github";
import { type Ctx, istDay, istText } from "../app";
import { getJob, isPaused, jobKey } from "../jobs/runtime";
import { dispatchJob, queueJob, type TickDeps } from "./tick";

export function scheduleRoutes(
  ctx: Ctx,
  opts: { github?: GithubBot; workflowFor?: TickDeps["workflowFor"] } = {},
) {
  const app = new Hono();
  const github = () => opts.github ?? githubFromEnv(ctx.env as Record<string, string | undefined>);

  app.post("/api/job/press", ctx.guard.person, async (c) => {
    const req = JobPressRequest.safeParse(await c.req.json().catch(() => undefined));
    if (!req.success) return c.json({ error: "bad body" }, 400);
    const { kind, subject, rerun } = req.data;
    const day = istDay(ctx.now());
    const from = req.data.from ?? day;
    const to = req.data.to ?? from;
    if (from > to) return c.json({ error: "range ends before it starts" }, 400);
    if (await isPaused(ctx, kind)) return c.json({ error: `${kind} is paused` }, 423);
    const bot = github();
    if (!bot) return c.json({ error: "the dispatcher has no bot key yet" }, 503);

    const key = jobKey(kind, subject, day);
    const existing = await getJob(ctx, key);
    if (existing && !(rerun && existing.status !== "queued" && existing.status !== "running"))
      return c.json({ error: `duplicate: ${key} is ${existing.status}` }, 409);
    if (existing) {
      // Recompute: the same key goes back to queued; the old run's rows stay until the new run publishes.
      await ctx.d1
        .prepare(
          "update job_runs set status = 'queued', range_from = ?, range_to = ?, attempts = 0, queued_at = ?, dispatched_at = null, dispatch_count = 0, error = null, retry_at = null where key = ?",
        )
        .bind(from, to, istText(ctx.now()), key)
        .run();
    } else if (!(await queueJob(ctx, { kind, subject, day, from, to }))) {
      return c.json({ error: `duplicate: ${key} is queued` }, 409);
    }
    try {
      await dispatchJob(
        { github: bot, workflowFor: opts.workflowFor },
        { kind, subject, day, range_from: from, range_to: to },
      );
      await ctx.d1
        .prepare(
          "update job_runs set dispatched_at = ?, dispatch_count = dispatch_count + 1 where key = ?",
        )
        .bind(istText(ctx.now()), key)
        .run();
    } catch {
      // Left queued with no dispatch time: the next 5-minute tick dispatches it.
      return c.json(
        { error: "GitHub refused the dispatch; it will be tried again within 5 minutes", key },
        502,
      );
    }
    return c.json({ key, status: "queued", range: { from, to } });
  });

  return app;
}

export default function routes(ctx: Ctx) {
  return scheduleRoutes(ctx);
}
