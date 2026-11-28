import { z } from "zod";

/** Days from a call to its 3-month score. */
export const SCORE_DAYS = 91;
/** A close this far from the window's edge is "no data", not a result. */
export const PRICE_SLACK_DAYS = 7;

export const PostmortemCause = z.enum([
  "thesis_wrong",
  "risk_hit",
  "news_after",
  "market",
  "unknown",
]);

/** One post-mortem: a missed call (a Buy that did not beat the Nifty 50 over three months, or an Avoid that did)
 * gets exactly one, in English and Bengali. `source` "code" is the line written without a model. */
export const PostmortemRow = z.object({
  call_key: z.string().min(1),
  symbol: z.string().regex(/^[A-Z0-9][A-Z0-9&-]{0,19}$/),
  day: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  call: z.enum(["buy", "avoid"]),
  excess_pct: z.number(),
  cause: PostmortemCause,
  why_en: z.string().min(1),
  why_bn: z.string().min(1),
  evidence: z.array(z.string()),
  source: z.enum(["model", "code"]),
  model: z.string().nullable(),
});
export type PostmortemRow = z.infer<typeof PostmortemRow>;

const BENGALI = /[ঀ-৿]/;
export function postmortemRowCheck(r: PostmortemRow): string | null {
  if (!BENGALI.test(r.why_bn)) return "a post-mortem has no Bengali";
  if (r.source === "model" && r.cause !== "unknown" && r.evidence.length === 0)
    return "a cause without evidence";
  return null;
}

/** Whether a call missed, from how the stock did against the Nifty 50 over the window (percent points of excess). */
export function missed(call: "buy" | "avoid" | "watch", excessPct: number): boolean {
  if (call === "buy") return excessPct <= 0;
  if (call === "avoid") return excessPct > 0;
  return false;
}

/** The nightly portfolio note (the one private model exception). The Claude scheduled task writes it back through
 * the API with its own key; the engine stores the text and never sees what it was made from. */
export const NightlyNote = z.object({
  day: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  text_en: z.string().min(1).max(4000),
  text_bn: z.string().min(1).max(8000),
});
export type NightlyNote = z.infer<typeof NightlyNote>;

export function nightlyNoteCheck(n: NightlyNote): string | null {
  return BENGALI.test(n.text_bn) ? null : "the note has no Bengali";
}
