import { z } from "zod";
import { IstTime } from "./time";

/** Every part writes one: running version, last success, last error, expected beat. */
export const Heartbeat = z.object({
  part: z.string().min(1),
  version: z.string().min(1),
  at: IstTime,
  ok: z.boolean(),
  error: z.string().nullable(),
  next_expected_by: IstTime.nullable(),
});
export type Heartbeat = z.infer<typeof Heartbeat>;
export const HeartbeatAck = z.object({ ok: z.literal(true) });
