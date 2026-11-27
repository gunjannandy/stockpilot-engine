import { z } from "zod";
import { IstTime } from "./time";

/** The Ping dataset's row: proof that a press (or a Job) reached the store and can be read back. */
export const PingRow = z.object({
  id: z.string().min(1),
  at: IstTime,
  source: z.enum(["button", "job"]),
});
export type PingRow = z.infer<typeof PingRow>;

export const PingLatest = z.object({
  latest: PingRow.nullable(),
  count: z.number().int().min(0),
});
export type PingLatest = z.infer<typeof PingLatest>;
