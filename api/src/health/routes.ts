import {
  type Colour,
  datasets,
  type HealthPart,
  Heartbeat,
  PARTS,
  PAUSE_RELEASES,
} from "@stockpilot/contract";
import { desc, eq } from "drizzle-orm";
import { Hono } from "hono";
import { checkResults, flags, heartbeats, writeBudget } from "../../drizzle/core";
import { depChecks, promiseResults } from "../../drizzle/ops";
import { type Ctx, istDay, istText, rawBody } from "../app";
import { latest as latestBackup } from "../backup/routes";
import { calendarStatus, loadCalendar } from "../calendar/routes";

const RANK: Record<Colour, number> = { green: 0, amber: 1, red: 2 };

export async function healthParts(ctx: Ctx): Promise<HealthPart[]> {
  const beats = new Map((await ctx.db.select().from(heartbeats)).map((b) => [b.part, b]));
  const now = istText(ctx.now());
  return PARTS.map((part): HealthPart => {
    if (part === "worker")
      return {
        part,
        status: "green",
        version: ctx.version,
        last_beat: now,
        last_success: now,
        error: null,
        next_expected_by: null,
        overdue: false,
      };
    const b = beats.get(part);
    if (!b)
      return {
        part,
        status: "amber",
        version: null,
        last_beat: null,
        last_success: null,
        error: "no beat yet",
        next_expected_by: null,
        overdue: false,
      };
    // IST text of one offset sorts as time, so a string compare is a time compare.
    const overdue = b.nextExpectedBy !== null && now > b.nextExpectedBy;
    return {
      part,
      version: b.version,
      last_beat: b.at,
      last_success: b.lastSuccess,
      error: b.error,
      next_expected_by: b.nextExpectedBy,
      overdue,
      status: !b.ok || overdue ? "red" : "green",
    };
  });
}

export default function routes(ctx: Ctx) {
  const app = new Hono();

  app.post("/api/heartbeat", ctx.guard.ingest, async (c) => {
    const req = Heartbeat.safeParse(JSON.parse(rawBody(c) || "null"));
    if (!req.success) return c.json({ error: "bad body" }, 400);
    const b = req.data;
    if (!(PARTS as readonly string[]).includes(b.part))
      return c.json({ error: "unknown part" }, 400);
    const row = {
      part: b.part,
      version: b.version,
      at: b.at,
      ok: b.ok,
      error: b.error,
      nextExpectedBy: b.next_expected_by,
    };
    await ctx.db
      .insert(heartbeats)
      .values({ ...row, lastSuccess: b.ok ? b.at : null })
      .onConflictDoUpdate({
        target: heartbeats.part,
        // a failed beat keeps the last success it had
        set: b.ok ? { ...row, lastSuccess: b.at } : row,
      });
    return c.json({ ok: true });
  });

  app.get("/api/health", ctx.guard.secret, async (c) => {
    const parts = await healthParts(ctx);
    // The calendar's own coverage check folds into its part: too few days ahead turns it amber.
    const cal = calendarStatus(await loadCalendar(ctx), istDay(ctx.now()));
    const calPart = parts.find((p) => p.part === "job.calendar");
    if (calPart && cal.status !== "green") {
      if (RANK[cal.status] > RANK[calPart.status]) calPart.status = cal.status;
      calPart.error = calPart.error ? `${calPart.error}; ${cal.message}` : cal.message;
    }
    const checks = (await ctx.db.select().from(checkResults).orderBy(checkResults.checkId)).map(
      (r) => ({
        id: r.checkId,
        ok: r.ok,
        at: r.at,
        detail: r.detail,
      }),
    );
    // Newest day first, so the first row seen per promise is its latest.
    const seen = new Set<string>();
    const promises = (await ctx.db.select().from(promiseResults).orderBy(desc(promiseResults.day)))
      .filter((r) => !seen.has(r.promise) && seen.add(r.promise))
      .map((r) => ({ promise: r.promise, day: r.day, ok: r.ok, detail: r.detail, at: r.at }))
      .sort((a, b) => a.promise.localeCompare(b.promise));
    const dependencies = (await ctx.db.select().from(depChecks).orderBy(depChecks.dep)).map(
      (r) => ({
        dep: r.dep,
        ok: r.ok,
        detail: r.detail,
        fallback: r.fallback,
        at: r.at,
      }),
    );
    const worst = parts.reduce<Colour>(
      (w, p) => (RANK[p.status] > RANK[w] ? p.status : w),
      "green",
    );
    const overall: Colour = checks.some((k) => !k.ok) ? "red" : worst;
    const backup = (await latestBackup(ctx)) as {
      backup: unknown;
      drill: unknown;
    };
    return c.json({
      at: istText(ctx.now()),
      version: ctx.version,
      overall,
      parts,
      checks,
      promises,
      dependencies,
      backup,
    });
  });

  // Public, no secret, no data: builders and dispatchers read check results and budgets here.
  app.get("/api/status", async (c) => {
    const checks = Object.fromEntries(
      (await ctx.db.select().from(checkResults)).map((r) => [r.checkId, { ok: r.ok, at: r.at }]),
    );
    const today = new Map(
      (
        await ctx.db
          .select()
          .from(writeBudget)
          .where(eq(writeBudget.day, istDay(ctx.now())))
      ).map((w) => [w.dataset, w.writes]),
    );
    const budgets = Object.fromEntries(
      Object.values(datasets).map((d) => {
        const used = today.get(d.name) ?? 0;
        return [
          d.name,
          { used, limit: d.writeBudget, percent: Math.round((used / d.writeBudget) * 1000) / 10 },
        ];
      }),
    );
    const [paused] = await ctx.db.select().from(flags).where(eq(flags.key, PAUSE_RELEASES));
    return c.json({
      at: istText(ctx.now()),
      version: ctx.version,
      paused: paused?.enabled === true,
      checks,
      budgets,
    });
  });

  return app;
}
