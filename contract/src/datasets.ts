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
  /** `private` datasets (holdings, trades, tax, feedback) never leave the owner's store: previews fill them with made-up rows only. Default public. */
  visibility?: "public" | "private";
  recomputable: boolean;
  /** Most D1 rows this dataset may write in a day (a row costs 1 + its indexes). */
  writeBudget: number;
  row: z.ZodType;
  /** `rows` (default, up to 1,000 per run) or `file`: one content-hashed file per run, only its pointer and summary in D1. */
  delivery?: "rows" | "file";
  /** Extra row check beyond `row`'s schema: a reason holds the row back and the run goes on. */
  rowCheck?: (row: Record<string, unknown>) => string | null;
  /** Run check: a reason fails the run. `rows` is present for `rows` delivery only. */
  runCheck?: (run: {
    rowCount: number;
    rows?: Record<string, unknown>[];
    summary: Record<string, unknown>;
  }) => string | null;
  /** Share of a run's rows that may be held back before the run fails (default 0.2). */
  heldBackLimit?: number;
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
