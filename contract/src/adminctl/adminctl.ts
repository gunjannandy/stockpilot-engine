import { z } from "zod";
import { JobKind } from "../core/jobs";
import { IsoDate } from "../core/time";

/** Admin's switches and the layout row, in one read. */
const Id = z.string().min(1).max(40);
export const PaneLayout = z.object({
  /** Pane ids in the order drawn; panes not listed follow in folder order. */
  order: z.array(Id).max(60).default([]),
  hidden: z.array(Id).max(60).default([]),
});
export const AdminLayout = z.object({
  rail: z.array(Id).max(40),
  hidden: z.array(Id).max(40).default([]),
  /** Per screen id: its panes' order and visibility. */
  panes: z.record(Id, PaneLayout).default({}),
});
export type AdminLayout = z.infer<typeof AdminLayout>;

export const AdminState = z.object({
  release_paused: z.boolean(),
  paused_kinds: z.array(JobKind),
  flags: z.record(z.string(), z.boolean()),
  layout: AdminLayout.nullable(),
});
export type AdminState = z.infer<typeof AdminState>;

export const ReleasePauseRequest = z.object({ paused: z.boolean() });
export const ReleasePauseResponse = ReleasePauseRequest;
export const JobPauseAdminRequest = z.object({ kind: JobKind, paused: z.boolean() });

/** Recompute the last N days (today included) of one recomputable dataset. */
export const RecomputeRequest = z.object({
  dataset: z.string().min(1).max(60),
  days: z.number().int().min(1).max(366),
});
export const RecomputeResponse = z.object({
  key: z.string(),
  status: z.literal("queued"),
  range: z.object({ from: IsoDate, to: IsoDate }),
});

/** Routes the Admin screen uses. All need a signed-in person. */
export const ADMIN_ROUTES = {
  state: "GET /api/admin/state",
  release_pause: "PUT /api/admin/release-pause",
  job_pause: "PUT /api/admin/job-pause",
  flag: "PUT /api/admin/flags",
  layout: "PUT /api/admin/layout",
  recompute: "POST /api/admin/recompute",
} as const;
