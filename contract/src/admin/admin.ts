import { z } from "zod";
import { IstTime } from "../core/time";

/** One count of a click: a screen, and optionally one button on it. Names only, never content. */
export const UsageHit = z.object({
  screen: z.string().min(1).max(40),
  button: z.string().min(1).max(60).optional(),
});
export type UsageHit = z.infer<typeof UsageHit>;
export const UsageStored = z.object({ screen: z.string(), button: z.string(), n: z.number() });

export const AdminFreshness = z.object({
  dataset: z.string(),
  job: z.string(),
  schedule: z.string(),
  updated_at: IstTime.nullable(),
  window_hours: z.number(),
  state: z.enum(["fresh", "stale", "never"]),
});
export const AdminRun = z.object({
  key: z.string(),
  kind: z.string(),
  day: z.string(),
  status: z.enum(["queued", "running", "done", "failed"]),
  attempts: z.number(),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
  error: z.string().nullable(),
  trail: z.array(z.object({ at: z.string().nullable(), text: z.string() })),
});
export const AdminProblem = z.object({
  id: z.string(),
  at: IstTime,
  message: z.string(),
  pane: z.string().nullable(),
  url: z.string().nullable(),
});
export const AdminNeed = z.object({ id: z.string(), text: z.string(), kind: z.string() });
export const AdminUsage = z.object({ screen: z.string(), button: z.string(), n: z.number() });

export const AdminOverview = z.object({
  at: IstTime,
  needs_you: z.array(AdminNeed),
  freshness: z.array(AdminFreshness),
  runs: z.array(AdminRun),
  problems: z.array(AdminProblem),
  usage: z.array(AdminUsage),
});
export type AdminOverview = z.infer<typeof AdminOverview>;

export const AdminRetry = z.object({ key: z.string().min(1).max(200) });
