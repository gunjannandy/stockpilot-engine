import { z } from "zod";
import { IstTime } from "./time";

/** Every part that must beat. A part that is missing from this list is not watched. */
export const PARTS = [
  "worker",
  "job.ping",
  "check_runner",
  "duty.scheduler",
  "duty.quotes",
  "duty.watcher",
  "duty.digest",
  "job.calendar",
  "job.backup",
  "job.drill",
] as const;
export type Part = (typeof PARTS)[number];

export const Colour = z.enum(["green", "amber", "red"]);
export type Colour = z.infer<typeof Colour>;

export const HealthPart = z.object({
  part: z.string(),
  status: Colour,
  version: z.string().nullable(),
  last_beat: IstTime.nullable(),
  last_success: IstTime.nullable(),
  error: z.string().nullable(),
  next_expected_by: IstTime.nullable(),
  overdue: z.boolean(),
});
export type HealthPart = z.infer<typeof HealthPart>;

export const CheckResult = z.object({
  id: z.string().regex(/^C-\d{3}-\d+$/),
  ok: z.boolean(),
  at: IstTime,
  detail: z.string(),
});
export type CheckResult = z.infer<typeof CheckResult>;

/** The latest backup or drill report (the same shape /api/backup serves); null before the first. */
export const BackupReport = z.object({
  at: z.string(),
  ok: z.boolean(),
  detail: z.string(),
  tables: z.record(z.string(), z.unknown()),
});
export type BackupReport = z.infer<typeof BackupReport>;

/** Behind the health secret header: every part's colour, the running version, stored check results. */
export const HealthResponse = z.object({
  at: IstTime,
  version: z.string(),
  overall: Colour,
  parts: z.array(HealthPart),
  checks: z.array(CheckResult),
  /** /api/backup, shown here so one page tells whether the vault and its restore proof are fresh. */
  backup: z.object({ backup: BackupReport.nullable(), drill: BackupReport.nullable() }),
});
export type HealthResponse = z.infer<typeof HealthResponse>;
