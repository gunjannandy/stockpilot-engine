import { z } from "zod";

/** The bench's pass lines (decisions: Haiku stays the model for forecasts only above both). */
export const BENCH_FORM_MIN = 0.95;
export const BENCH_VERDICT_MIN = 0.8;

export const AnalyseCallWord = z.enum(["buy", "watch", "avoid"]);

const Pair = z.object({ text_en: z.string(), text_bn: z.string() });
const Reason = Pair.extend({ evidence: z.array(z.string()) });

/** What the Analyse Job writes for one stock and day. `source` "code" means the code-only call stands
 * (no model answer, or the answer failed its checks); `note` says why. The brief behind it carries no
 * holding or tax field: the call card adds the "if you act" and tax lines in the browser. */
export const AnalyseCall = z.object({
  symbol: z.string().regex(/^[A-Z0-9][A-Z0-9&-]{0,19}$/),
  day: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  call: AnalyseCallWord,
  chance_pct: z.number().min(0).max(100),
  source: z.enum(["model", "code"]),
  summary_en: z.string().nullable(),
  summary_bn: z.string().nullable(),
  reasons: z.array(Reason).max(3),
  risks: z.array(Pair).max(3),
  model: z.string().nullable(),
  note: z.string().nullable(),
});
export type AnalyseCall = z.infer<typeof AnalyseCall>;

const BENGALI = /[ঀ-৿]/;

/** The first reason a call is refused at the door, or null: a model answer always has Bengali beside its English. */
export function analyseCallCheck(c: AnalyseCall): string | null {
  if (c.source === "model") {
    if (!c.summary_en || !c.summary_bn || !BENGALI.test(c.summary_bn))
      return "a model call has no Bengali";
    if (c.reasons.some((r) => !BENGALI.test(r.text_bn))) return "a reason has no Bengali";
  }
  if (c.source === "code" && (c.summary_en || c.summary_bn))
    return "a code-only call carries no model text";
  return null;
}
