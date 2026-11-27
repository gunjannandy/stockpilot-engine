import { z } from "zod";
import { IsoDate, IstTime } from "./time";

/** Ingest door: write-only, one batch of rows for one dataset, tagged with the run's id. */
export const IngestRequest = z.object({
  dataset: z.string().min(1),
  run_id: z.string().min(1),
  rows: z.array(z.record(z.string(), z.unknown())).max(5000),
});
export const IngestResponse = z.object({
  accepted: z.number().int().min(0),
  held_back: z.number().int().min(0),
});

export const JobStartRequest = z.object({ kind: z.string().min(1), run_id: z.string().min(1) });
export const JobStartResponse = z.object({ run_id: z.string(), started_at: IstTime });

export const JobFinishRequest = z.object({
  run_id: z.string().min(1),
  status: z.enum(["done", "failed"]),
  result: z.string().nullable(),
  error: z.string().nullable(),
});
export const JobFinishResponse = z.object({ ok: z.literal(true) });

/** What Python reads to decide whether today is worth running. */
export const MarketStatus = z.object({
  date: IsoDate,
  is_trading_day: z.boolean(),
  reason: z.string().nullable(),
});
