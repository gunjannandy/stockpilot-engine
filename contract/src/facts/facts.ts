import { z } from "zod";

/** Fewer stocks than this and the run fails: the sources broke. */
export const FACTS_MIN = 100;

const num = z.number().nullable();

/** One raw figure behind the analysis: what it is, its value, the period it covers and where it came from. */
export const Figure = z.object({
  metric: z.string().min(1),
  value: z.number(),
  /** Last day of the period the figure covers, YYYY-MM-DD. */
  period: z.string(),
  /** nse and bse are filings; yfinance only fills a gap. */
  source: z.string().min(1),
});
export type Figure = z.infer<typeof Figure>;

/** One plain sentence, in English and Kolkata Bengali. `key` names its template. */
export const Sentence = z.object({ key: z.string().min(1), en: z.string(), bn: z.string() });
export type Sentence = z.infer<typeof Sentence>;

/** One row of the `facts` dataset: a stock's metrics with the sector comparison, plain sentences and raw figures.
 * Percent values are percent. Anything the sources did not give is null, never zero. Arrays are JSON text
 * because a row's fields are table columns; read them with `factSentences` and `factFigures`. */
export const FactsRow = z.object({
  id: z.string().min(1),
  symbol: z.string().min(1),
  exchange: z.string().min(1),
  name: z.string(),
  sector: z.string(),
  as_of: z.string(),
  pe: num,
  /** Middle P/E of the sector; null with fewer than five peers. */
  pe_sector: num,
  pb: num,
  dividend_yield_pct: num,
  market_cap_cr: num,
  sales_growth_yoy_pct: num,
  profit_growth_yoy_pct: num,
  roe_pct: num,
  roce_pct: num,
  debt_to_equity: num,
  promoter_pct: num,
  pledge_pct: num,
  sentences_json: z.string(),
  figures_json: z.string(),
  /** JSON list of up to five symbols of the same sector, nearest by market cap. */
  similar_json: z.string().default("[]"),
  /** Metrics with no figure, `|` separated. */
  not_available: z.string(),
});
export type FactsRow = z.infer<typeof FactsRow>;

function list<T>(text: string, schema: z.ZodType<T>): T[] {
  try {
    const v: unknown = JSON.parse(text);
    if (!Array.isArray(v)) return [];
    return v.flatMap((x) => {
      const p = schema.safeParse(x);
      return p.success ? [p.data] : [];
    });
  } catch {
    return [];
  }
}
export const factSentences = (t: string): Sentence[] => list(t, Sentence);
export const factFigures = (t: string): Figure[] => list(t, Figure);

export const factSimilar = (t: string): string[] => list(t, z.string());

export const FactsResponse = z.object({
  as_of: z.string().nullable(),
  facts: FactsRow.omit({ sentences_json: true, figures_json: true, similar_json: true })
    .extend({
      sentences: z.array(Sentence),
      figures: z.array(Figure),
      similar: z.array(z.string()),
    })
    .nullable(),
});
export type FactsResponse = z.infer<typeof FactsResponse>;

/** The first reason a row cannot be used, or null. */
export function factsRowCheck(r: Record<string, unknown>): string | null {
  if (!r.symbol || !r.exchange) return "symbol and exchange are required";
  if (factFigures(String(r.figures_json ?? "")).length < 1) return "no raw figure";
  const bn = factSentences(String(r.sentences_json ?? "")).find((s) => !/[ঀ-৿]/.test(s.bn));
  if (bn) return `sentence ${bn.key} has no Bengali`;
  return null;
}
