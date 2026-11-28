import { z } from "zod";

/** Scored calls before a number is called a lean, and before it is called a result (v2's rule, kept). */
export const RECORD_TOO_EARLY = 30;
export const RECORD_LEAN_UNTIL = 100;
/** A call beat the Nifty when its excess return was over this over the horizon (round-trip cost and tax allowance). */
export const BEAT_HURDLE = 0.01;
/** Calendar days a call's window runs, by its horizon in trading days. */
export const WINDOW_DAYS: Record<number, number> = { 63: 91, 126: 182 };

export const ScoreRow = z.object({
  call_id: z.string().min(1),
  beat: z.boolean(),
  scored_on: z.string(),
  /** Returns over the call's window as fractions: the stock, the Nifty, and the watchlist's equal-weight average (null when it had no prices). */
  stock_ret: z.number(),
  nifty_ret: z.number(),
  equal_ret: z.number().nullable(),
});
export type ScoreRow = z.infer<typeof ScoreRow>;

/** Are we adding value: our Buy calls against holding the Nifty and an equal-weight watchlist, over the same windows.
 * Percent values are percent. `adding` is null until there are 30 scored Buy calls. */
export const AddingValue = z.object({
  n: z.number().int().min(0),
  ours_pct: z.number().nullable(),
  nifty_pct: z.number().nullable(),
  equal_weight_pct: z.number().nullable(),
  edge_vs_nifty_pct: z.number().nullable(),
  edge_vs_equal_weight_pct: z.number().nullable(),
  adding: z.boolean().nullable(),
});
export type AddingValue = z.infer<typeof AddingValue>;

/** What the Job posts: the scores of calls whose window has ended. */
export const RecordRequest = z.object({ scores: z.array(ScoreRow).max(5000) });
export type RecordRequest = z.infer<typeof RecordRequest>;

export const recordVerdict = (n: number): "too early" | "a lean" | "a result" =>
  n < RECORD_TOO_EARLY ? "too early" : n < RECORD_LEAN_UNTIL ? "a lean" : "a result";

const Bin = z.object({ said: z.number(), happened: z.number(), n: z.number().int() });

export const TrackLine = z.object({
  horizon_days: z.number().int(),
  n: z.number().int(),
  /** Of the Buy calls, the share that beat the Nifty. */
  buy_n: z.number().int(),
  buy_hit_rate: z.number().nullable(),
  brier: z.number().nullable(),
  base_brier: z.number().nullable(),
  calibration: z.array(Bin),
  verdict: z.enum(["too early", "a lean", "a result"]),
  line: z.object({ en: z.string(), bn: z.string() }),
});
export type TrackLine = z.infer<typeof TrackLine>;

export const RecordResponse = z.object({
  lines: z.array(TrackLine),
  value: AddingValue.nullable(),
});
export type RecordResponse = z.infer<typeof RecordResponse>;

/** The sentence under a track-record line, in both languages. */
export function trackSentence(
  n: number,
  months: number,
  hit: number | null,
  brier: number | null,
  base: number | null,
): { en: string; bn: string } {
  if (n < RECORD_TOO_EARLY)
    return {
      en: `Calls over ${months} months: ${n} scored so far, too early to say how good they are (we wait for ${RECORD_TOO_EARLY}).`,
      bn: `${months} মাসের কল: এখন পর্যন্ত ${n}টির ফল মিলেছে, কেমন তা বলার জন্য এখনও তাড়াতাড়ি (আমরা ${RECORD_TOO_EARLY}টির জন্য অপেক্ষা করি)।`,
    };
  const v = recordVerdict(n);
  const vbn = v === "a lean" ? "একটি ইঙ্গিত" : "একটি ফল";
  if (hit === null || brier === null || base === null)
    return {
      en: `Calls over ${months} months: ${n} scored.`,
      bn: `${months} মাসের কল: ${n}টির ফল মিলেছে।`,
    };
  const better = brier < base;
  return {
    en: `Calls over ${months} months: ${n} scored, ${Math.round(hit * 100)}% of Buy calls beat the Nifty, Brier ${brier.toFixed(3)}, ${better ? "better than" : "no better than"} the base rate alone (${base.toFixed(3)}); ${v}.`,
    bn: `${months} মাসের কল: ${n}টির ফল মিলেছে, কেনার কলের ${Math.round(hit * 100)}% নিফটিকে হারিয়েছে, ব্রায়ার ${brier.toFixed(3)}, শুধু গড় হারের (${base.toFixed(3)}) চেয়ে ${better ? "ভালো" : "ভালো নয়"}; ${vbn}।`,
  };
}

/** Adding value from the Buy calls' average returns (fractions). `adding` stays null under 30 scored Buy calls. */
export function addingValue(
  n: number,
  stock: number | null,
  nifty: number | null,
  equal: number | null,
): AddingValue {
  const pct = (x: number | null) => (x === null ? null : Math.round(x * 10000) / 100);
  const edgeN = stock === null || nifty === null ? null : stock - nifty;
  const edgeE = stock === null || equal === null ? null : stock - equal;
  return {
    n,
    ours_pct: pct(stock),
    nifty_pct: pct(nifty),
    equal_weight_pct: pct(equal),
    edge_vs_nifty_pct: pct(edgeN),
    edge_vs_equal_weight_pct: pct(edgeE),
    adding:
      n < RECORD_TOO_EARLY || edgeN === null ? null : edgeN > 0 && (edgeE === null || edgeE > 0),
  };
}

/** One row a day for the `record_runs` dataset: what the scoring Job did, so the 5-minute tick can start it and health can see it ran. */
export const RecordRun = z.object({
  id: z.string().min(1),
  day: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  scored: z.number().int().min(0),
});
export type RecordRun = z.infer<typeof RecordRun>;
