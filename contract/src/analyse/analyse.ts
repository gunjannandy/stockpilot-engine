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

const Rate = z.number().min(0).max(1);

/** What the bench Job reports after scoring the Analyse method on its past public briefs. `red` holds the plain
 * reasons it failed (empty when green); a red report pauses releases. `comparison` is the Haiku comparison from the
 * first run: `forecast_model` is the model forecasts use (Haiku only above both lines). */
export const BenchReport = z.object({
  fingerprint: z.string().min(1),
  model: z.string().min(1),
  scores: z.object({
    n: z.number().int().min(1),
    form_ok: z.number().int().min(0),
    form_rate: Rate,
    hit_rate: Rate.nullable(),
    decided: z.number().int().min(0),
    code_hit_rate: Rate.nullable(),
  }),
  problems: z.record(z.string(), z.array(z.string())),
  comparison: z
    .object({
      form_rate: Rate,
      agreement: Rate,
      passed: z.boolean(),
      forecast_model: z.enum(["haiku", "sonnet"]),
    })
    .nullable(),
  forecast_model: z.enum(["haiku", "sonnet"]),
  red: z.array(z.string()),
});
export type BenchReport = z.infer<typeof BenchReport>;

/** The comparison's verdict, from its two numbers. The Job and the Worker both use this one rule. */
export function benchComparisonPasses(formRate: number, agreement: number): boolean {
  return formRate >= BENCH_FORM_MIN && agreement >= BENCH_VERDICT_MIN;
}

/** What the fund Analyse Job writes for one fund and day: the same shape as a stock call, with buy or watch only. */
export const FundAnalyseCall = AnalyseCall.omit({ symbol: true, call: true }).extend({
  fund: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9:_.-]{0,60}$/),
  call: z.enum(["buy", "watch"]),
});
export type FundAnalyseCall = z.infer<typeof FundAnalyseCall>;
