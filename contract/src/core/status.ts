import { z } from "zod";
import { IstTime } from "./time";

/** Public and free of data: builders and dispatchers read it, so it carries no private value. */
export const StatusResponse = z.object({
  at: IstTime,
  version: z.string(),
  paused: z.boolean(),
  checks: z.record(z.string(), z.object({ ok: z.boolean(), at: IstTime })),
  budgets: z.record(
    z.string(),
    z.object({ used: z.number().int(), limit: z.number().int(), percent: z.number() }),
  ),
});
export type StatusResponse = z.infer<typeof StatusResponse>;

export const ChecksRunResponse = z.object({
  results: z.array(z.object({ id: z.string(), ok: z.boolean(), detail: z.string() })),
});

/** One promoted UI PR's note, English and Bengali, shown once to the readers. */
export const WhatsNewLine = z.object({ pr: z.number().int(), en: z.string().min(1), bn: z.string().min(1) });
export const WhatsNewPost = z.object({ lines: z.array(WhatsNewLine).max(50) });
export const WhatsNewStored = z.object({ stored: z.number().int().min(0) });
export const WhatsNewList = z.object({
  lines: z.array(WhatsNewLine.extend({ at: IstTime })),
});
