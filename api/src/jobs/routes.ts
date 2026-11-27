// The Job runtime's routes: Jobs begin and end here (signed), people press, pause and look.
import {
  IsoDate,
  JobBeginRequest,
  JobEndRequest,
  JobPauseRequest,
  ModelAnswerRequest,
  ModelClaimRequest,
} from "@stockpilot/contract";
import { Hono } from "hono";
import { type Ctx, istDay, istText, rawBody } from "../app";
import {
  claimModel,
  MODEL_DAILY_CAP,
  modelStatus,
  NEXT_UPDATE_TOMORROW,
  storeAnswer,
} from "./models";
import { beginJob, endJob, expectedSeconds, getJob, jobKey } from "./runtime";

const parse = (raw: string): unknown => {
  try {
    return JSON.parse(raw);
  } catch {
    return undefined;
  }
};

export function jobRoutes(ctx: Ctx, opts: { caps?: Record<string, number> } = {}) {
  const caps = opts.caps ?? MODEL_DAILY_CAP;
  const app = new Hono();

  app.post("/api/job/begin", ctx.guard.ingest, async (c) => {
    const req = JobBeginRequest.safeParse(parse(rawBody(c)));
    if (!req.success) return c.json({ error: "bad body" }, 400);
    const day = req.data.day ?? istDay(ctx.now());
    const from = req.data.from ?? day;
    const to = req.data.to ?? from;
    if (from > to) return c.json({ error: "range ends before it starts" }, 400);
    const r = await beginJob(ctx, {
      kind: req.data.kind,
      subject: req.data.subject,
      day,
      runId: req.data.run_id,
      from,
      to,
      rerun: req.data.rerun ?? false,
    });
    if (!r.ok) return c.json({ error: r.error }, r.status);
    return c.json({
      run_id: req.data.run_id,
      key: r.key,
      started_at: r.startedAt,
      expected_seconds: await expectedSeconds(ctx, req.data.kind),
      range: r.range,
    });
  });

  app.post("/api/job/end", ctx.guard.ingest, async (c) => {
    const req = JobEndRequest.safeParse(parse(rawBody(c)));
    if (!req.success) return c.json({ error: "bad body" }, 400);
    const r = await endJob(ctx, {
      runId: req.data.run_id,
      status: req.data.status,
      result: req.data.result,
      error: req.data.error,
    });
    if (!r.ok) return c.json({ error: "no running Job with that id" }, 404);
    return c.json({ ok: true, retry_at: r.retryAt ?? null });
  });

  // Admin's switch: pause or resume one kind.
  app.post("/api/job/pause", ctx.guard.person, async (c) => {
    const req = JobPauseRequest.safeParse(await c.req.json().catch(() => undefined));
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

  app.get("/api/job/run", ctx.guard.person, async (c) => {
    const key = c.req.query("key") ?? "";
    const day = c.req.query("day");
    const row = await getJob(
      ctx,
      key ||
        jobKey(
          c.req.query("kind") ?? "",
          c.req.query("subject") ?? "all",
          day && IsoDate.safeParse(day).success ? day : istDay(ctx.now()),
        ),
    );
    return row ? c.json(row) : c.json({ error: "no such Job" }, 404);
  });

  // ---- the model gate ----
  app.post("/api/model/claim", ctx.guard.ingest, async (c) => {
    const req = ModelClaimRequest.safeParse(parse(rawBody(c)));
    if (!req.success) return c.json({ error: "bad body" }, 400);
    const r = await claimModel(ctx, caps, {
      kind: req.data.kind,
      model: req.data.model,
      brief: req.data.brief_hash,
    });
    if (r.cached) return c.json({ cached: true, answer: r.answer });
    if (!r.allowed)
      return c.json({ error: "daily cap reached", message: NEXT_UPDATE_TOMORROW }, 429);
    return c.json({ cached: false, left: r.left });
  });

  app.post("/api/model/answer", ctx.guard.ingest, async (c) => {
    const req = ModelAnswerRequest.safeParse(parse(rawBody(c)));
    if (!req.success) return c.json({ error: "bad body" }, 400);
    await storeAnswer(ctx, {
      kind: req.data.kind,
      model: req.data.model,
      brief: req.data.brief_hash,
      answer: req.data.answer,
    });
    return c.json({ ok: true });
  });

  app.get("/api/model/status", ctx.guard.person, async (c) =>
    c.json(await modelStatus(ctx, caps, c.req.query("kind") ?? "")),
  );

  return app;
}

export default function routes(ctx: Ctx) {
  return jobRoutes(ctx);
}
