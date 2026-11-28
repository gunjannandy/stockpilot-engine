import { z } from "zod";
import { IsoDate } from "./time";

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

/** What Python reads to decide whether today is worth running. */
export const MarketStatus = z.object({
  date: IsoDate,
  is_trading_day: z.boolean(),
  reason: z.string().nullable(),
});
