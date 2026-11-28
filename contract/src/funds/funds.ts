import { z } from "zod";
import { IsoDate } from "../core/time";

/** Most funds one run publishes: the door takes 1,000 rows a day and a held-back row also costs a write. */
export const FUNDS_MAX = 900;
/** Fewer funds than this and the run fails: something upstream broke. */
export const FUNDS_MIN = 100;

/** One row of the `funds` dataset: a fund (its Direct Growth scheme) with its costs, returns and weekly NAVs.
 * Percent values are percent (12.5 = 12.5%). Anything the sources did not give is null, never zero. */
export const FundRow = z.object({
  id: z.string().min(1),
  /** The scheme code NAVs are read by. */
  code: z.number().int(),
  name: z.string().min(1),
  amc: z.string().nullable(),
  category: z.string().nullable(),
  nav: z.number().nullable(),
  nav_date: IsoDate.nullable(),
  /** Yearly cost in percent, Direct plan (and Regular, to show what the Direct plan saves). */
  ter: z.number().nullable(),
  ter_regular: z.number().nullable(),
  /** Fund size in rupees crore. */
  aum_cr: z.number().nullable(),
  /** Yearly return over the last 1, 3 and 5 years; null when the fund is younger. */
  r1: z.number().nullable(),
  r3: z.number().nullable(),
  r5: z.number().nullable(),
  /** The middle fund of the category over the same spans, and how many funds made that category. */
  cat_r1: z.number().nullable(),
  cat_r3: z.number().nullable(),
  cat_r5: z.number().nullable(),
  category_n: z.number().int(),
  /** Worst fall from a peak to a later low in the NAV history, percent (negative). */
  max_fall: z.number().nullable(),
  /** Rolling 1-year return across month ends: worst, middle and best, and the share of windows below zero. */
  roll_min: z.number().nullable(),
  roll_median: z.number().nullable(),
  roll_max: z.number().nullable(),
  roll_loss_share: z.number().nullable(),
  /** Weekly NAV, oldest first, as JSON text: [[day, NAV], ...]. Text because a row's fields are table columns
   * (a column cannot hold an array); read it with `fundNavs`. */
  navs_json: z.string(),
});
export type FundRow = z.infer<typeof FundRow>;

/** A fund as the list shows it: the row without its NAV history. */
export type FundSummary = Omit<FundRow, "navs_json">;

/** The NAV history of a row as [day, NAV] pairs; empty when the text is not a list of pairs. */
export function fundNavs(navsJson: string): [string, number][] {
  try {
    const v: unknown = JSON.parse(navsJson);
    if (!Array.isArray(v)) return [];
    return v.filter(
      (p): p is [string, number] =>
        Array.isArray(p) && typeof p[0] === "string" && typeof p[1] === "number",
    );
  } catch {
    return [];
  }
}

/** The first reason a row cannot be used, or null. */
export function fundRowCheck(r: Record<string, unknown>): string | null {
  if (fundNavs(String(r.navs_json ?? "")).length < 2) return "fewer than two NAVs";
  for (const k of ["ter", "ter_regular", "aum_cr"])
    if (typeof r[k] === "number" && (r[k] as number) < 0) return `${k} is negative`;
  return null;
}
