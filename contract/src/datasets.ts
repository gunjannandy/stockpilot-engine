import type { z } from "zod";
import type { JobKind } from "./core/jobs";
import { PingRow } from "./core/ping";

/** One line per dataset (decisions §2 Publishing). Python validates rows against `row`'s generated
 * JSON Schema; the door enforces `writeBudget` per day. */
export type Dataset = {
  /** Registry key, also the ingest door's `dataset` value. */
  name: string;
  /** The Job that produces it. */
  job: JobKind;
  table: string;
  /** Plain-words schedule. */
  schedule: string;
  /** How stale it may get before health turns amber. */
  freshnessHours: number;
  /** Data checks: a row check holds a row back; a run check fails the run. */
  checks: { row: string[]; run: string[] };
  recomputable: boolean;
  /** Most D1 rows this dataset may write in a day (a row costs 1 + its indexes). */
  writeBudget: number;
  row: z.ZodType;
};

export const datasets = {
  ping: {
    name: "ping",
    job: "ping",
    table: "ping",
    schedule: "on press, and when the Ping Job runs",
    freshnessHours: 24 * 365,
    checks: { row: ["id is not empty", "at is IST"], run: [] },
    recomputable: false,
    writeBudget: 200,
    row: PingRow,
  },
} as const satisfies Record<string, Dataset>;
export type DatasetName = keyof typeof datasets;
