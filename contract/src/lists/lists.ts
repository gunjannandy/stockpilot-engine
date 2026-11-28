import { z } from "zod";
import { CallView } from "../calls/calls";
import { IstTime } from "../core/time";

/** The lists of Worth following. `you_hold` needs the holdings, which the public Job never sees: the browser builds it
 * from `money`. The other five come from the lists Job. */
export const PUBLIC_LISTS = ["top10", "just_missed", "has_view", "falling", "busy_today"] as const;
export const ListId = z.enum(PUBLIC_LISTS);
export type ListId = z.infer<typeof ListId>;
export const LIST_IDS = [
  "top10",
  "just_missed",
  "has_view",
  "you_hold",
  "falling",
  "busy_today",
] as const;

export const TOP_N = 10;
/** The list Job reruns this often through market hours (minutes). */
export const LISTS_EVERY_MINUTES = 30;
/** A stock that moved this much (percent) from yesterday's close is busy today. */
export const BUSY_MOVE_PCT = 3;

export const ListReason = z.object({ key: z.string().min(1), en: z.string(), bn: z.string() });
export type ListReason = z.infer<typeof ListReason>;

/** One row of the `lists` dataset: a stock's place in one list with its reasons (templates, English and Bengali).
 * `reasons_json` is JSON text because a row's fields are table columns. */
export const ListRow = z.object({
  id: z.string().min(1),
  list: ListId,
  symbol: z.string().min(1),
  exchange: z.enum(["NSE", "BSE"]),
  position: z.number().int().min(1),
  reasons_json: z.string(),
  updated_at: IstTime,
});
export type ListRow = z.infer<typeof ListRow>;

export function listReasons(text: string): ListReason[] {
  try {
    const v: unknown = JSON.parse(text);
    if (!Array.isArray(v)) return [];
    return v.flatMap((x) => {
      const p = ListReason.safeParse(x);
      return p.success ? [p.data] : [];
    });
  } catch {
    return [];
  }
}

/** The first reason a list row is held back, or null: every row carries a reason, each in Bengali too. */
export function listRowCheck(r: Record<string, unknown>): string | null {
  if (r.id !== `${r.list}:${r.symbol}`) return "id must be list:symbol";
  const reasons = listReasons(String(r.reasons_json ?? ""));
  if (reasons.length < 1) return "a row without a reason";
  const bad = reasons.find((x) => !/[ঀ-৿]/.test(x.bn));
  if (bad) return `reason ${bad.key} has no Bengali`;
  return null;
}

export const LISTS_MIN_TOP = TOP_N;

/** What the Worth following pane reads. */
export const ListsResponse = z.object({
  /** Stocks analysed and the number that passed our checks, from the latest screen run. Null before the first run. */
  counts: z
    .object({ analysed: z.number().int(), passed: z.number().int(), as_of: z.string() })
    .nullable(),
  lists: z.array(
    z.object({
      list: ListId,
      updated_at: IstTime.nullable(),
      rows: z.array(ListRow.extend({ call: CallView.nullable() })),
    }),
  ),
});
export type ListsResponse = z.infer<typeof ListsResponse>;

/** Not now lasts a week or a month. */
export const NOT_NOW_FOR = { week: 7, month: 30 } as const;
export const NotNowRequest = z.object({
  symbol: z.string().min(1),
  for: z.enum(["week", "month"]),
});
export const StarRequest = z.object({
  /** A stock's symbol or a fund's ISIN. */
  id: z.string().min(1).max(40),
  kind: z.enum(["stock", "fund"]),
  name: z.string().max(120).optional(),
});
export type StarRequest = z.infer<typeof StarRequest>;

export const WatchItem = z.object({
  id: z.string(),
  kind: z.enum(["stock", "fund"]),
  name: z.string().nullable(),
  added_at: IstTime,
  /** Our view of a stock (its latest call); null for a fund or a stock with no call. */
  call: CallView.nullable(),
});
export const WatchlistResponse = z.object({
  items: z.array(WatchItem),
  not_now: z.array(z.object({ symbol: z.string(), until: IstTime, created_at: IstTime })),
});
export type WatchlistResponse = z.infer<typeof WatchlistResponse>;
