import { z } from "zod";

/** The seven verdicts a call can carry (story 31). */
export const VERDICTS = ["Sell", "Weak", "Hold", "Watch", "Buy", "Trim", "No view yet"] as const;
export const Verdict = z.enum(VERDICTS);
export type Verdict = z.infer<typeof Verdict>;

/** A call's chance of beating the Nifty must sit inside this band: 5% and 95% are never stated as sure. */
export const CHANCE_MIN = 0.05;
export const CHANCE_MAX = 0.95;
/** Fewest past cases a base rate may rest on. */
export const BASE_CASES_MIN = 30;
/** A bucket that moved more than this many points since the backtest note is called limited evidence. */
export const BUCKET_MOVE_POINTS = 8;
/** Share of a run's calls that may be held back before the run fails. */
export const CALLS_HELD_LIMIT = 0.1;
export const LIMITED_EVIDENCE = "limited evidence";
export const LIMITED_EVIDENCE_BN = "প্রমাণ সীমিত";

const num = z.number().nullable();

/** A sentence made from a template, in English and Kolkata Bengali. `key` names its template. */
export const CallSentence = z.object({ key: z.string().min(1), en: z.string(), bn: z.string() });
export type CallSentence = z.infer<typeof CallSentence>;

/** One call. Append-only: a new call is a new row (id = symbol:day:run); nothing updates an old one. Chance is a
 * fraction (0.62 is 62 in 100). Levels are rupees. Lists are JSON text because a row's fields are table columns;
 * read them with `callSentences`. */
export const CallRow = z.object({
  id: z.string().min(1),
  symbol: z.string().min(1),
  exchange: z.enum(["NSE", "BSE"]),
  /** Day the call was made, YYYY-MM-DD. */
  made_on: z.string(),
  verdict: Verdict,
  /** Chance of beating the Nifty over the horizon; null only with the verdict "No view yet". */
  chance: num,
  /** The horizon in trading days; 63 (3 months) or 126 (6 months). */
  horizon_days: z.number().int().min(1),
  /** Past cases the base rate rests on. */
  base_cases: z.number().int().min(0),
  base_rate: num,
  /** Sell line and buy line the chance is read against. */
  sell_line: z.number(),
  buy_line: z.number(),
  /** What it could rise to, what we would buy at, and sell at once if it falls to. Rupees. */
  could_rise_to: num,
  would_buy_at: num,
  sell_at_once_at: num,
  /** True when the bucket is thin or moved; the text then carries "limited evidence". */
  limited: z.boolean(),
  /** Why, what could go wrong, we would buy if: template sentences, JSON text. */
  sentences_json: z.string(),
  /** Past calls like this one: how many, and how many beat the Nifty. */
  similar_n: z.number().int().min(0),
  similar_beat: z.number().int().min(0),
  model_version: z.string(),
});
export type CallRow = z.infer<typeof CallRow>;

export function callSentences(text: string): CallSentence[] {
  try {
    const v: unknown = JSON.parse(text);
    if (!Array.isArray(v)) return [];
    return v.flatMap((x) => {
      const p = CallSentence.safeParse(x);
      return p.success ? [p.data] : [];
    });
  } catch {
    return [];
  }
}

/** The first reason a call must be held back, or null (C-170-1). */
export function callRowCheck(r: Record<string, unknown>): string | null {
  if (r.verdict !== "No view yet") {
    const c = r.chance;
    if (typeof c !== "number") return "a call with a view carries a chance";
    if (c < CHANCE_MIN || c > CHANCE_MAX) return "chance outside 5% to 95%";
    if (typeof r.base_cases !== "number" || r.base_cases < BASE_CASES_MIN)
      return "base rate rests on fewer than 30 cases";
  }
  if (typeof r.horizon_days !== "number" || r.horizon_days < 1) return "no horizon";
  const s = callSentences(String(r.sentences_json ?? ""));
  const bad = s.find((x) => !/[ঀ-৿]/.test(x.bn));
  if (bad) return `sentence ${bad.key} has no Bengali`;
  if (r.limited === true && !s.some((x) => /limited evidence/i.test(x.en)))
    return 'a thin or moved bucket needs "limited evidence" in the text';
  return null;
}

/** The confidence line: "our last 24 calls like this: 15 beat the Nifty". */
export function confidenceLine(n: number, beat: number): { en: string; bn: string } | null {
  if (n < 1) return null;
  return {
    en: `Our last ${n} calls like this: ${beat} beat the Nifty.`,
    bn: `এমন আমাদের শেষ ${n}টি কলের মধ্যে ${beat}টি নিফটিকে হারিয়েছে।`,
  };
}

/** Whether a bucket is thin (fewer cases than the base-rate floor) or moved more than 8 points. */
export function bucketLimited(
  cases: number,
  rateNow: number | null,
  rateNote: number | null,
): boolean {
  if (cases < BASE_CASES_MIN) return true;
  if (rateNow === null || rateNote === null) return false;
  return Math.abs(rateNow - rateNote) * 100 > BUCKET_MOVE_POINTS;
}

/** The request the forecast Job sends to the append-only calls door. */
export const CallsRequest = z.object({ rows: z.array(CallRow).max(1000) });
export type CallsRequest = z.infer<typeof CallsRequest>;

/** A call as the screen reads it: the row plus its confidence line (null when no past call is like it). */
export const CallView = CallRow.extend({
  confidence: z.object({ en: z.string(), bn: z.string() }).nullable(),
});
export type CallView = z.infer<typeof CallView>;

export const CallsResponse = z.object({ as_of: z.string().nullable(), calls: z.array(CallView) });
export type CallsResponse = z.infer<typeof CallsResponse>;

export const CallHistoryResponse = z.object({ symbol: z.string(), calls: z.array(CallView) });
export type CallHistoryResponse = z.infer<typeof CallHistoryResponse>;

export const CompareResponse = z.object({
  a: CallView.nullable(),
  b: CallView.nullable(),
});
export type CompareResponse = z.infer<typeof CompareResponse>;

/** One row of the nightly screen file: a stock's rank on four factors, each a percentile in its industry. */
export const ScreenRow = z.object({
  symbol: z.string().min(1),
  exchange: z.enum(["NSE", "BSE"]),
  industry: z.string(),
  quality: num,
  value: num,
  momentum: num,
  risk: num,
  score: num,
  rank: z.number().int().min(1).nullable(),
  /** Why a stock was left out, or null when it passed. */
  excluded: z.string().nullable(),
});
export type ScreenRow = z.infer<typeof ScreenRow>;

/** The screen is one content-hashed file per run; its D1 row holds the pointer and this summary. */
export const ScreenSummary = z.object({
  analysed: z.number().int().min(0),
  passed: z.number().int().min(0),
});
export type ScreenSummary = z.infer<typeof ScreenSummary>;

/** One row a day for the `calls_runs` dataset: what the forecast Job did, so the 5-minute tick can start it and
 * health can see it ran. The calls themselves go through the append-only calls door, never this dataset. */
export const CallsRun = z.object({
  id: z.string().min(1),
  day: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  written: z.number().int().min(0),
  held_back: z.number().int().min(0),
});
export type CallsRun = z.infer<typeof CallsRun>;

/** Fewer stocks than this in a screen file and the run fails: the sources broke. */
export const SCREEN_MIN = 100;
