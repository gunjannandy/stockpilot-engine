import { z } from "zod";
import { JobKind } from "../core/jobs";
import { IsoDate, IstTime } from "../core/time";

/** Retries a failed Job gets before it waits for a person (decisions §6). */
export const JOB_MAX_ATTEMPTS = 3;
/** A dispatched Job not started within this many minutes is dispatched again. */
export const DISPATCH_GRACE_MINUTES = 3;

const Ident = z.string().regex(/^[A-Za-z0-9_.:-]{1,80}$/);

/** A Job starts: unique by (kind, subject, day). `from` and `to` are the date range it covers (default: the day). */
export const JobBeginRequest = z.object({
  kind: JobKind,
  subject: Ident.default("all"),
  day: IsoDate.optional(),
  run_id: z.string().min(1),
  from: IsoDate.optional(),
  to: IsoDate.optional(),
  /** Admin's Recompute: run again although the key already ran. */
  rerun: z.boolean().optional(),
});
export const JobBeginResponse = z.object({
  run_id: z.string(),
  key: z.string(),
  started_at: IstTime,
  /** From the median of the last five finished runs of the kind; null with none yet. */
  expected_seconds: z.number().int().nullable(),
  range: z.object({ from: IsoDate, to: IsoDate }),
});

export const JobEndRequest = z.object({
  run_id: z.string().min(1),
  status: z.enum(["done", "failed"]),
  result: z.string().nullable().optional(),
  error: z.string().nullable().optional(),
});

export const JobEndResponse = z.object({ ok: z.literal(true), retry_at: IstTime.nullable() });

/** A press on a button Job (Analyse, load a stock, Refresh, Recompute): dispatched at once. */
export const JobPressRequest = z.object({
  kind: JobKind,
  subject: Ident,
  from: IsoDate.optional(),
  to: IsoDate.optional(),
  rerun: z.boolean().optional(),
});

export const JobPauseRequest = z.object({ kind: JobKind, paused: z.boolean() });

/** The model gate: a Job asks before spending a model call, and stores the answer after. */
export const ModelClaimRequest = z.object({
  kind: JobKind,
  model: z.string().min(1),
  /** sha256 of the brief, computed by the caller. */
  brief_hash: z.string().min(1).max(200),
});
export const ModelAnswerRequest = ModelClaimRequest.extend({ answer: z.string() });
