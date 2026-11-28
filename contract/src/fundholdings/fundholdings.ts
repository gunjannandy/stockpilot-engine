import { z } from "zod";
import { IsoDate } from "../core/time";

/** Most funds one run publishes: the door takes 1,000 rows a day. */
export const FUND_HOLDINGS_MAX = 900;
/** Fewer funds than this and the run fails: the houses' files moved or the reader broke. */
export const FUND_HOLDINGS_MIN = 20;

/** One row of the `fund_holdings` dataset: a fund's latest monthly portfolio, as published by its fund house.
 * Public data only; which of these stocks anyone holds is matched in the browser with `fundOverlap`. */
export const FundHoldingsRow = z.object({
  /** The same id the `funds` dataset uses. */
  id: z.string().min(1),
  name: z.string().min(1),
  amc: z.string().nullable(),
  /** The month-end the house's file is "as on". */
  as_of: IsoDate.nullable(),
  /** Holdings as JSON text: [[isin, name, percent of the fund's value or null], ...]. Text because a row's
   * fields are table columns; read it with `fundHoldings`. */
  holdings_json: z.string(),
});
export type FundHoldingsRow = z.infer<typeof FundHoldingsRow>;

export type FundHolding = { isin: string; name: string; pct_nav: number | null };

/** The holdings of a row; empty when the text is not a list of [isin, name, pct]. */
export function fundHoldings(holdingsJson: string): FundHolding[] {
  try {
    const v: unknown = JSON.parse(holdingsJson);
    if (!Array.isArray(v)) return [];
    const out: FundHolding[] = [];
    for (const p of v) {
      if (Array.isArray(p) && typeof p[0] === "string" && typeof p[1] === "string")
        out.push({ isin: p[0], name: p[1], pct_nav: typeof p[2] === "number" ? p[2] : null });
    }
    return out;
  } catch {
    return [];
  }
}

export type FundOverlap = {
  shared: FundHolding[];
  n_shared: number;
  n_held: number;
  /** The fund's own weight in the shared stocks, percent. */
  pct_nav: number;
  /** Share of the fund's equity lines (INE ISINs) that are shared, percent. */
  pct_of_fund_stocks: number;
};

/** How much of a fund is stocks the person holds. Pure: the screen calls it with the person's ISINs, so no
 * holding ever leaves the browser. */
export function fundOverlap(holdings: FundHolding[], heldIsins: Iterable<string>): FundOverlap {
  const held = new Set([...heldIsins].map((i) => i.toUpperCase()));
  const shared = holdings.filter((h) => held.has(h.isin.toUpperCase()));
  const equities = holdings.filter((h) => h.isin.toUpperCase().startsWith("INE"));
  const pct = shared.reduce((s, h) => s + (h.pct_nav ?? 0), 0);
  const eqShared = equities.filter((h) => held.has(h.isin.toUpperCase())).length;
  return {
    shared,
    n_shared: shared.length,
    n_held: held.size,
    pct_nav: Math.round(pct * 100) / 100,
    pct_of_fund_stocks: equities.length ? Math.round((1000 * eqShared) / equities.length) / 10 : 0,
  };
}

/** The first reason a row cannot be used, or null. */
export function fundHoldingsRowCheck(r: Record<string, unknown>): string | null {
  return fundHoldings(String(r.holdings_json ?? "")).length === 0 ? "no holdings" : null;
}
