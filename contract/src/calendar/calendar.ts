import { z } from "zod";
import { IsoDate } from "../core/time";

/** Fewer days than this ahead and the calendar is amber: the next holiday list is overdue. */
export const CALENDAR_MIN_DAYS_AHEAD = 30;

export const CALENDAR_KINDS = [
  "holiday",
  "special",
  "split",
  "bonus",
  "symbol_change",
  "delisting",
] as const;

/** One row of the `calendar` dataset, flat like every dataset row: a closed day, a special session, or a
 * corporate action. Which of the optional fields a kind needs is checked by `calendarRowCheck`. */
export const CalendarRow = z.object({
  id: z.string().min(1),
  kind: z.enum(CALENDAR_KINDS),
  /** The day itself (holiday, special session) or the ex-date (corporate action). */
  date: IsoDate,
  reason: z.string().nullable(),
  symbol: z.string().nullable(),
  /** split: one old share becomes `new_shares`. bonus: `new_shares` free for every `old_shares` held. */
  old_shares: z.number().int().nullable(),
  new_shares: z.number().int().nullable(),
  new_symbol: z.string().nullable(),
});
export type CalendarRow = z.infer<typeof CalendarRow>;

/** What the calendar module works with: a row with the fields its kind needs, or nothing. */
export type CalendarEntry =
  | { id: string; kind: "holiday" | "special"; date: string; reason: string }
  | {
      id: string;
      kind: "split" | "bonus";
      date: string;
      symbol: string;
      old_shares: number;
      new_shares: number;
    }
  | { id: string; kind: "symbol_change"; date: string; symbol: string; new_symbol: string }
  | { id: string; kind: "delisting"; date: string; symbol: string };

/** The first reason a row cannot be used, or null. */
export function calendarRowCheck(r: Record<string, unknown>): string | null {
  const has = (k: string) => r[k] !== null && r[k] !== undefined && r[k] !== "";
  const need = (...ks: string[]) => ks.find((k) => !has(k));
  const kind = r.kind as string;
  const missing =
    kind === "holiday" || kind === "special"
      ? need("reason")
      : kind === "split" || kind === "bonus"
        ? need("symbol", "old_shares", "new_shares")
        : kind === "symbol_change"
          ? need("symbol", "new_symbol")
          : kind === "delisting"
            ? need("symbol")
            : "kind";
  if (missing) return `${kind} needs ${missing}`;
  if (
    (kind === "split" || kind === "bonus") &&
    ((r.old_shares as number) < 1 || (r.new_shares as number) < 1)
  )
    return `${kind} share counts must be at least 1`;
  return null;
}

/** A stored row as a usable entry, or null when its kind's fields are missing. */
export function calendarEntry(row: CalendarRow): CalendarEntry | null {
  if (calendarRowCheck(row)) return null;
  const base = { id: row.id, date: row.date };
  switch (row.kind) {
    case "holiday":
    case "special":
      return { ...base, kind: row.kind, reason: row.reason as string };
    case "split":
    case "bonus":
      return {
        ...base,
        kind: row.kind,
        symbol: row.symbol as string,
        old_shares: row.old_shares as number,
        new_shares: row.new_shares as number,
      };
    case "symbol_change":
      return {
        ...base,
        kind: row.kind,
        symbol: row.symbol as string,
        new_symbol: row.new_symbol as string,
      };
    case "delisting":
      return { ...base, kind: row.kind, symbol: row.symbol as string };
  }
}

export const CalendarStatus = z.object({
  status: z.enum(["green", "amber"]),
  /** Last day the calendar covers (the latest holiday or special session it lists), or null when empty. */
  covered_until: IsoDate.nullable(),
  days_ahead: z.number().int(),
  message: z.string(),
});
export type CalendarStatus = z.infer<typeof CalendarStatus>;
