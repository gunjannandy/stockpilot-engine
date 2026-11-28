import { z } from "zod";
import { IsoDate } from "../core/time";

/** Fewer rows than this and the run fails: the funds feeding it broke. */
export const FUND_CALLS_MIN = 5;

/** One row of the `fund_calls` dataset, from public NAV history only (held funds are matched privately).
 * `kind` "call": a fund called "buy" or "watch" (its id is the fund's id in `funds`). `kind` "track": the
 * track record, how often funds of a kind and 3-year quartile beat their category's middle fund over the next
 * 12 months at past checkpoints (id `track:<kind>:<quartile>`). `chance`, `cases` and `periods` are null when
 * too few cases back them: never a made-up rate. */
export const FundCallRow = z.object({
  id: z.string().min(1),
  kind: z.enum(["call", "track"]),
  name: z.string().min(1),
  category: z.string().nullable(),
  call: z.enum(["buy", "watch"]).nullable(),
  /** 3-year rank inside the category, and how many funds were ranked. */
  rank: z.number().int().nullable(),
  of: z.number().int().nullable(),
  quartile: z.number().int().min(1).max(4),
  /** Share of past cases that beat the category's middle fund over 12 months (0 to 1). */
  chance: z.number().min(0).max(1).nullable(),
  cases: z.number().int().nullable(),
  periods: z.number().int().nullable(),
  /** Average excess over the middle fund in those cases, percentage points. */
  avg_excess: z.number().nullable(),
  /** Plain-words reasons a Buy was held back to Watch, joined with "; ". */
  reasons: z.string(),
  caveat: z.string(),
  as_of: IsoDate,
});
export type FundCallRow = z.infer<typeof FundCallRow>;

export function fundCallRowCheck(r: Record<string, unknown>): string | null {
  if (r.kind === "call" && r.call == null) return "a call row has no call";
  if (r.kind === "track" && r.call != null) return "a track row has a call";
  if (r.chance != null && (r.cases == null || r.periods == null))
    return "a chance without its cases";
  return null;
}
