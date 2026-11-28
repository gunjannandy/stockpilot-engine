// Sync: tap, log in to Kite, the callback stores raw holdings and trades (read endpoints only) and says
// how many things changed. Refresh: the button starts the documents workflow in the private repo.
import type { SyncStatus } from "@stockpilot/contract";
import { Hono } from "hono";
import { type GithubBot, githubFromEnv } from "../../../adapters/src/github";
import { type KiteClient, kiteFromEnv } from "../../../adapters/src/kite";
import { type Ctx, istDay, istText } from "../app";
import { getJob, isPaused, jobKey } from "../jobs/runtime";
import { queueJob } from "../schedule/tick";
import { lastSync, storeSync } from "./sync";

export const PRIVATE_REPO = "stockpilot-hq/stockpilot";
export const DOCUMENTS_WORKFLOW = "documents.yml";

export function kiteRoutes(ctx: Ctx, opts: { kite?: KiteClient; github?: GithubBot } = {}) {
  const app = new Hono();
  const envOf = () => ctx.env as Record<string, string | undefined>;
  const kite = () => opts.kite ?? kiteFromEnv(envOf());
  const github = () => opts.github ?? githubFromEnv(envOf());

  app.get("/kite/login", ctx.guard.person, (c) => {
    const k = kite();
    if (!k) return c.json({ error: "Kite is not set up yet." }, 503);
    return c.redirect(k.loginUrl(), 302);
  });

  app.get("/kite/callback", ctx.guard.person, async (c) => {
    const k = kite();
    if (!k) return c.json({ error: "Kite is not set up yet." }, 503);
    const requestToken = c.req.query("request_token");
    if (!requestToken || c.req.query("status") === "error")
      return c.json({ error: "Kite login did not complete." }, 400);
    const token = await k.exchange(requestToken);
    if (!token) return c.json({ error: "Kite refused the login. Press Sync to try again." }, 502);
    let stored: Awaited<ReturnType<typeof storeSync>>;
    try {
      stored = await storeSync(ctx, await k.read(token));
    } catch {
      return c.json({ error: "Kite did not answer. Press Sync to try again." }, 502);
    }
    return c.redirect(`/sync?synced=1&changes=${stored.changes}`, 302);
  });

  app.get("/api/sync", ctx.guard.person, async (c) => {
    const last = await lastSync(ctx);
    const status: SyncStatus = {
      synced_at: last?.fetched_at ?? null,
      changes: last?.changes ?? null,
      steps: last
        ? [
            { id: "login", state: "ok", count: null },
            { id: "holdings", state: "ok", count: last.holdings },
            { id: "trades", state: "ok", count: last.trades },
            { id: "done", state: "ok", count: last.changes ?? 0 },
          ]
        : [],
    };
    return c.json(status);
  });

  // Refresh: one documents run per day key; a press while one is queued or running changes nothing.
  app.post("/api/refresh", ctx.guard.person, async (c) => {
    // Written now, started by nothing until cutover: the Worker dispatches only once this is switched on.
    if (envOf().DOCUMENTS_LIVE !== "1") return c.json({ error: "Refresh starts at cutover." }, 503);
    if (await isPaused(ctx, "documents")) return c.json({ error: "documents is paused" }, 423);
    const bot = github();
    if (!bot) return c.json({ error: "the dispatcher has no bot key yet" }, 503);
    const day = istDay(ctx.now());
    const key = jobKey("documents", "drive", day);
    const existing = await getJob(ctx, key);
    if (existing && (existing.status === "queued" || existing.status === "running"))
      return c.json({ error: `duplicate: ${key} is ${existing.status}` }, 409);
    if (existing) {
      await ctx.d1
        .prepare(
          "update job_runs set status = 'queued', attempts = 0, queued_at = ?, dispatched_at = null, dispatch_count = 0, error = null, retry_at = null where key = ?",
        )
        .bind(istText(ctx.now()), key)
        .run();
    } else {
      await queueJob(ctx, { kind: "documents", subject: "drive", day });
    }
    try {
      await bot.dispatchWorkflow({
        repo: PRIVATE_REPO,
        workflow: DOCUMENTS_WORKFLOW,
        ref: "main",
        inputs: { kind: "documents", subject: "drive", day, from: day, to: day },
      });
      await ctx.d1
        .prepare(
          "update job_runs set dispatched_at = ?, dispatch_count = dispatch_count + 1 where key = ?",
        )
        .bind(istText(ctx.now()), key)
        .run();
    } catch {
      return c.json({ error: "GitHub refused the dispatch. Press Refresh again.", key }, 502);
    }
    return c.json({ key, status: "queued" });
  });

  return app;
}

export default function routes(ctx: Ctx) {
  return kiteRoutes(ctx);
}
