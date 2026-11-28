// Admin's backend: release pause, pause per Job kind, feature flags, the layout row, Recompute last N days.
import {
  AdminLayout,
  type AdminState,
  datasets,
  FlagWrite,
  JobPauseAdminRequest,
  PAUSE_RELEASES,
  RecomputeRequest,
  ReleasePauseRequest,
} from "@stockpilot/contract";
import { drizzle } from "drizzle-orm/d1";
import { Hono } from "hono";
import type { GithubBot } from "../../../adapters/src/github";
import { flags } from "../../drizzle/core";
import { layout } from "../../drizzle/layout";
import { type Ctx, istDay, istText } from "../app";
import { scheduleRoutes } from "../schedule/routes";

const DAY = 86_400_000;
const json = async (c: { req: { json: () => Promise<unknown> } }) =>
  c.req.json().catch(() => undefined);

export function adminRoutes(ctx: Ctx, opts: { github?: GithubBot } = {}) {
  const app = new Hono();
  const db = drizzle(ctx.d1);
  const setFlag = async (key: string, enabled: boolean) => {
    const row = { key, enabled, updatedAt: istText(ctx.now()) };
    await ctx.db.insert(flags).values(row).onConflictDoUpdate({ target: flags.key, set: row });
  };

  app.get("/api/admin/state", ctx.guard.person, async (c) => {
    const rows = await ctx.db.select().from(flags);
    const fl = Object.fromEntries(rows.map((r) => [r.key, r.enabled]));
    const pauses = (await ctx.d1.prepare("select kind from job_pauses order by kind").all()) as {
      results: { kind: string }[];
    };
    const [l] = await db.select().from(layout).limit(1);
    const parsed = l ? AdminLayout.safeParse(JSON.parse(l.json)) : null;
    const state = {
      release_paused: fl[PAUSE_RELEASES] === true,
      paused_kinds: pauses.results.map((r) => r.kind),
      flags: fl,
      layout: parsed?.success ? parsed.data : null,
    } as AdminState;
    return c.json(state);
  });

  app.put("/api/admin/release-pause", ctx.guard.person, async (c) => {
    const req = ReleasePauseRequest.safeParse(await json(c));
    if (!req.success) return c.json({ error: "bad body" }, 400);
    await setFlag(PAUSE_RELEASES, req.data.paused);
    return c.json({ paused: req.data.paused });
  });

  app.put("/api/admin/job-pause", ctx.guard.person, async (c) => {
    const req = JobPauseAdminRequest.safeParse(await json(c));
    if (!req.success) return c.json({ error: "bad body" }, 400);
    await ctx.d1
      .prepare(
        req.data.paused
          ? "insert or replace into job_pauses (kind, paused_at) values (?, ?)"
          : "delete from job_pauses where kind = ? and ? is not null",
      )
      .bind(req.data.kind, istText(ctx.now()))
      .run();
    return c.json({ kind: req.data.kind, paused: req.data.paused });
  });

  app.put("/api/admin/flags", ctx.guard.person, async (c) => {
    const req = FlagWrite.safeParse(await json(c));
    if (!req.success) return c.json({ error: "bad body" }, 400);
    await setFlag(req.data.key, req.data.enabled);
    return c.json(req.data);
  });

  app.put("/api/admin/layout", ctx.guard.person, async (c) => {
    const body = AdminLayout.safeParse(await json(c));
    if (!body.success) return c.json({ error: "bad body" }, 400);
    const row = { key: "default", json: JSON.stringify(body.data), updatedAt: istText(ctx.now()) };
    await db.insert(layout).values(row).onConflictDoUpdate({ target: layout.key, set: row });
    return c.json({ layout: body.data });
  });

  // Recompute: one Job through the button path (pause, duplicate and dispatch rules stay in one place).
  app.post("/api/admin/recompute", ctx.guard.person, async (c) => {
    const req = RecomputeRequest.safeParse(await json(c));
    if (!req.success) return c.json({ error: "bad body" }, 400);
    const ds = (datasets as Record<string, (typeof datasets)[keyof typeof datasets]>)[
      req.data.dataset
    ];
    if (!ds) return c.json({ error: "no such dataset" }, 404);
    if (!ds.recomputable) return c.json({ error: `${ds.name} cannot be recomputed` }, 400);
    const to = istDay(ctx.now());
    const from = istDay(new Date(ctx.now().getTime() - (req.data.days - 1) * DAY));
    const headers = new Headers(c.req.raw.headers);
    headers.delete("content-length");
    headers.set("content-type", "application/json");
    return scheduleRoutes(ctx, { github: opts.github }).request("/api/job/press", {
      method: "POST",
      headers,
      body: JSON.stringify({ kind: ds.job, subject: ds.name, from, to, rerun: true }),
    });
  });

  return app;
}

export default function routes(ctx: Ctx) {
  return adminRoutes(ctx);
}
