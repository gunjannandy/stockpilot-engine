import { z } from "zod";
import { IstTime } from "./time";

/** Job kinds that run as batch work. Kinds that moved into the Worker (watchlist, Not now, budget,
 * feedback) and the dropped weekly review are gone (decisions §3, §7). */
export const JobKind = z.enum([
  "sync",
  "documents",
  "analyse",
  "refresh_call",
  "news_tag",
  "news_rank",
  "load_stock",
  "news_collect",
  "history_backfill",
  "nightly",
  "backup",
  "drill",
  "ping",
  "calendar",
  "funds",
  "fundholdings",
  "universe",
  "history",
  "facts",
]);
export type JobKind = z.infer<typeof JobKind>;

export const JobStatus = z.enum(["queued", "running", "done", "failed"]);

export const Job = z.object({
  id: z.string(),
  kind: JobKind,
  asked_by: z.enum(["owner", "father", "system"]),
  status: JobStatus,
  result: z.string().nullable(),
  error: z.string().nullable(),
  error_bn: z.string().nullable(),
  created_at: IstTime,
  started_at: IstTime.nullable(),
  finished_at: IstTime.nullable(),
});
export type Job = z.infer<typeof Job>;

/** A writer appends progress lines and never edits one; seq starts at 1 with no gaps. */
export const ProgressLine = z.object({
  run_id: z.string(),
  seq: z.number().int().min(1),
  at: IstTime,
  state: z.enum(["info", "ok", "fail"]),
  text: z.string(),
  text_bn: z.string().nullable(),
});
export type ProgressLine = z.infer<typeof ProgressLine>;
