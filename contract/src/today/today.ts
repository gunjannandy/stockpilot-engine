import { z } from "zod";

const num = z.number().nullable();

/** Fewer large stocks than this and breadth is left empty rather than guessed. */
export const BREADTH_MIN = 100;
/** Median P/E edges for the value band: under the first is cheap, over the second dear. */
export const VALUE_BAND_EDGES = [18, 24] as const;

/** One row a day of the `market` dataset: the market's health. A figure the sources did not give is null, never zero. */
export const MarketRow = z.object({
  id: z.string().min(1),
  day: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  nifty_close: num,
  /** The Nifty's distance from its 200-day average, percent. */
  nifty_trend_pct: num,
  nifty_trend: z.enum(["up", "down"]).nullable(),
  /** Share of the largest stocks above their own 200-day average, percent, and how many were counted. */
  breadth_pct: num,
  breadth_n: z.number().int().min(0),
  /** Middle P/E of stocks with a profit, and where it sits: cheap, fair or dear. */
  median_pe: num,
  value_band: z.enum(["cheap", "fair", "dear"]).nullable(),
  /** Plain sentences, English and Kolkata Bengali: JSON text of {key, en, bn}. */
  sentences_json: z.string(),
});
export type MarketRow = z.infer<typeof MarketRow>;

export function marketRowCheck(r: Record<string, unknown>): string | null {
  if (r.nifty_trend_pct === null && r.breadth_pct === null && r.median_pe === null)
    return "no figure at all";
  try {
    const s = JSON.parse(String(r.sentences_json ?? "[]")) as { bn?: string }[];
    if (!s.length) return "no sentence";
    if (s.some((x) => !/[ঀ-৿]/.test(x.bn ?? ""))) return "a sentence has no Bengali";
  } catch {
    return "sentences are not JSON";
  }
  return null;
}

export const TodayCall = z.object({
  symbol: z.string(),
  verdict: z.string(),
  chance: num,
  made_on: z.string(),
});

/** Groups of stocks by verdict: Sell, Weak, Fine keep (Hold), Close to a buy (Watch), and Unusual today (busy). */
export const TODAY_GROUPS = ["sell", "weak", "fine_keep", "close_to_buy", "unusual"] as const;

export const TodayResponse = z.object({
  /** The one call line for the day; the morning email carries the same text. */
  call_line: z.object({
    kind: z.enum(["sell", "buy", "nothing"]),
    en: z.string(),
    bn: z.string(),
    symbols: z.array(z.string()),
  }),
  /** Money left this month (rupees); null when no budget is set. Not a headline: Settings owns it. */
  money_left_inr: z.number().nullable(),
  market: MarketRow.omit({ sentences_json: true })
    .extend({ sentences: z.array(z.object({ key: z.string(), en: z.string(), bn: z.string() })) })
    .nullable(),
  groups: z.object({
    sell: z.array(z.string()),
    weak: z.array(z.string()),
    fine_keep: z.array(z.string()),
    close_to_buy: z.array(z.string()),
    unusual: z.array(z.string()),
  }),
  /** Newest call day; stocks held with no call dated after the last trading day show in `stale_held`. */
  as_of: z.string().nullable(),
  stale_held: z.array(z.string()),
});
export type TodayResponse = z.infer<typeof TodayResponse>;
