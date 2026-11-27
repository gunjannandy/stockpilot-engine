import { z } from "zod";
import { IsoDate, IstTime } from "../core/time";

/** The most rows a dataset may publish as rows. Over it, a run publishes one file (decisions §2). */
export const ROWS_LIMIT = 1000;
/** Share of D1's daily writes (free plan: 100,000) the publishing door may use. The rest is kept for
 * people's own writes: stars, Not now, feedback, Sync. */
export const D1_DAILY_WRITES = 100_000;
export const DOOR_WRITE_SHARE = 0.8;

/** Provenance every batch carries: where the rows came from, when they were fetched, what date they describe. */
const Provenance = {
  dataset: z.string().min(1),
  run_id: z.string().min(1),
  source: z.string().min(1),
  fetched_at: IstTime,
  as_of: z.union([IsoDate, IstTime]),
};

/** A batch of rows for one run of one dataset. */
export const PublishRowsRequest = z.object({
  ...Provenance,
  rows: z.array(z.record(z.string(), z.unknown())).max(5000),
});
export const PublishRowsResponse = z.object({
  accepted: z.number().int().min(0),
  held_back: z.number().int().min(0),
});

/** The one file a big dataset publishes per run: its name carries the first 12 hex digits of its sha256. */
export const PublishedFile = z.object({
  name: z.string().regex(/^[a-z][a-z0-9_]*\.[0-9a-f]{12}\.json$/),
  sha256: z.string().regex(/^[0-9a-f]{64}$/),
  rows: z.number().int().min(0),
});

export const PublishFinishRequest = z.object({
  dataset: z.string().min(1),
  run_id: z.string().min(1),
  /** File datasets only; `source`, `fetched_at` and `as_of` are then required here, as no rows came first. */
  source: z.string().min(1).optional(),
  fetched_at: IstTime.optional(),
  as_of: z.union([IsoDate, IstTime]).optional(),
  file: PublishedFile.optional(),
  /** File datasets: rows the Job held back, so the threshold still applies. */
  held_back: z.number().int().min(0).optional(),
  summary: z.record(z.string(), z.unknown()).optional(),
});
export const PublishFinishResponse = z.object({
  published: z.boolean(),
  run_id: z.string(),
  reason: z.string().nullable(),
  /** The run screens are served now, with its date. */
  serving: z.object({ run_id: z.string(), as_of: z.string() }).nullable(),
});

/** What a pane or screen reads for one dataset: the current run's rows (or its file) with the run's date. */
export const DatasetAnswer = z.object({
  dataset: z.string(),
  run_id: z.string().nullable(),
  as_of: z.string().nullable(),
  published_at: z.string().nullable(),
  rows: z.array(z.unknown()),
  file: z.string().nullable(),
  summary: z.record(z.string(), z.unknown()),
});
