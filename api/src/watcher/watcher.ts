// The watcher duty (decisions §6) and post-deploy smoke (§5 Safety). Every 15 minutes: one issue per
// trouble episode, as stockpilot-bot; and a red inside the first hour of a version rolls it back.
import { type Colour, PAUSE_RELEASES } from "@stockpilot/contract";
import { drizzle } from "drizzle-orm/d1";
import type { Platform } from "../../../adapters/src/cloudflare";
import type { GithubBot } from "../../../adapters/src/github";
import * as core from "../../drizzle/core";
import { type Ctx, istText } from "../app";
import { healthParts } from "../health/routes";
import type { Core } from "../jobs/runtime";

export const PRIVATE_REPO = "stockpilot-hq/stockpilot";
export const SMOKE_WINDOW_MINUTES = 60;
/** Browser errors in the last 15 minutes that count as a spike. */
export const ERROR_SPIKE = 10;
const MIN = 60_000;

export type Trouble = { subject: string; what: string };

/** What is red right now: parts, failed production checks, a browser-error spike. */
export async function currentTrouble(c: Core): Promise<Trouble[]> {
  const db = drizzle(c.d1, { schema: core });
  const ctx = { d1: c.d1, db, now: c.now, version: c.version, env: c.env } as unknown as Ctx;
  const out: Trouble[] = [];
  for (const p of await healthParts(ctx))
    if (p.status === ("red" satisfies Colour))
      out.push({
        subject: `part:${p.part}`,
        what: `${p.part} is red${p.error ? `: ${p.error}` : p.overdue ? ": its beat is overdue" : ""}`,
      });
  const checks = (await c.d1
    .prepare("select check_id, detail from check_results where ok = 0")
    .all()) as {
    results: { check_id: string; detail: string }[];
  };
  for (const k of checks.results)
    out.push({ subject: `check:${k.check_id}`, what: `check ${k.check_id} failed: ${k.detail}` });
  const since = istText(new Date(c.now().getTime() - 15 * MIN));
  const errs = (await c.d1
    .prepare("select count(*) as n from browser_errors where at >= ?")
    .bind(since)
    .first()) as { n: number } | null;
  if ((errs?.n ?? 0) >= ERROR_SPIKE)
    out.push({ subject: "browser-errors", what: `${errs?.n} browser errors in 15 minutes` });
  return out;
}

/** Open one issue per new trouble; close the episode when it turns green so a return opens a new one. */
export async function watch(c: Core, github: GithubBot, trouble?: Trouble[]) {
  const now = istText(c.now());
  const reds = trouble ?? (await currentTrouble(c));
  const open = (await c.d1
    .prepare("select subject from watcher_alerts where closed_at is null")
    .all()) as {
    results: { subject: string }[];
  };
  const openSet = new Set(open.results.map((r) => r.subject));
  const opened: number[] = [];
  for (const t of reds) {
    if (openSet.has(t.subject)) continue;
    // Insert first: only the insert that wins opens the issue, so two overlapping runs cannot double up.
    const claim = await c.d1
      .prepare(
        `insert into watcher_alerts (subject, issue, opened_at, closed_at) values (?, null, ?, null)
         on conflict(subject) do update set opened_at = excluded.opened_at, closed_at = null, issue = null
         where watcher_alerts.closed_at is not null`,
      )
      .bind(t.subject, now)
      .run();
    if (claim.meta.changes === 0) continue;
    try {
      const issue = await github.openIssue({
        repo: PRIVATE_REPO,
        title: `Watcher: ${t.what}`.slice(0, 120),
        body: `${t.what}\n\nSeen ${now} on version ${c.version}. The watcher opens one issue per episode and stays quiet until this turns green and red again.`,
        labels: ["watcher"],
      });
      await c.d1
        .prepare("update watcher_alerts set issue = ? where subject = ?")
        .bind(issue, t.subject)
        .run();
      opened.push(issue);
    } catch (err) {
      // Not opened: release the claim so the next run tries again.
      await c.d1
        .prepare("delete from watcher_alerts where subject = ? and issue is null")
        .bind(t.subject)
        .run();
      throw err;
    }
  }
  const redSet = new Set(reds.map((r) => r.subject));
  for (const s of openSet)
    if (!redSet.has(s))
      await c.d1
        .prepare("update watcher_alerts set closed_at = ? where subject = ?")
        .bind(now, s)
        .run();
  return { opened, red: reds.length };
}

/** Red within an hour of a version going live: roll back, open a `hotfix` issue, pause releases. Once per version. */
export async function smoke(
  c: Core,
  deps: { github: GithubBot; platform: Platform },
  trouble?: Trouble[],
) {
  const live = (await c.d1
    .prepare("select first_seen_at from deploys where version = ?")
    .bind(c.version)
    .first()) as { first_seen_at: string } | null;
  if (!live) return { rolledBack: false, why: "no deploy record" };
  const age = c.now().getTime() - Date.parse(live.first_seen_at);
  if (age > SMOKE_WINDOW_MINUTES * MIN) return { rolledBack: false, why: "past the first hour" };
  const reds = trouble ?? (await currentTrouble(c));
  if (reds.length === 0) return { rolledBack: false, why: "green" };
  const detail = reds
    .map((r) => r.what)
    .join("; ")
    .slice(0, 500);
  const at = istText(c.now());
  const claim = await c.d1
    .prepare("insert or ignore into rollbacks (version, at, detail, issue) values (?, ?, ?, null)")
    .bind(c.version, at, detail)
    .run();
  if (claim.meta.changes === 0) return { rolledBack: false, why: "already rolled back" };
  // Pause first: nothing else should promote while we undo this.
  await c.d1
    .prepare(
      "insert into flags (key, enabled, updated_at) values (?, 1, ?) on conflict(key) do update set enabled = 1, updated_at = excluded.updated_at",
    )
    .bind(PAUSE_RELEASES, at)
    .run();
  let error: string | null = null;
  try {
    await deps.platform.rollback();
  } catch (err) {
    error = err instanceof Error ? err.message : String(err);
  }
  const issue = await deps.github.openIssue({
    repo: PRIVATE_REPO,
    title: `Hotfix: ${c.version} went red in its first hour`.slice(0, 120),
    body: `${detail}\n\n${error ? `Rollback FAILED (${error}); roll back by hand.` : "Production was rolled back to the previous deployment."} Releases are paused until this is fixed.`,
    labels: ["hotfix"],
  });
  await c.d1
    .prepare("update rollbacks set issue = ? where version = ?")
    .bind(issue, c.version)
    .run();
  return { rolledBack: error === null, issue, why: error ?? "red" };
}
