import { z } from "zod";
import { RawHolding, RawTrade } from "../kite/kite";

/** A split, bonus, demerger or rights issue, with the terms NSE does not give (`terms` is null until known). */
export const RawAction = z.object({
  symbol: z.string().min(1),
  ex_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  kind: z.enum(["split", "bonus", "demerger", "rights"]),
  isin: z.string().nullable(),
  numerator: z.number(),
  denominator: z.number(),
  subject: z.string(),
  source: z.string(),
  terms: z
    .object({
      new_isin: z.string().nullable(),
      new_symbol: z.string().nullable(),
      cost_fraction: z.number().nullable(),
      price: z.number().nullable(),
    })
    .nullable(),
});
export type RawAction = z.infer<typeof RawAction>;

/** `GET /api/portfolio/holdings`: the latest snapshot of each source. The browser does the maths. */
export const HoldingsResponse = z.object({ holdings: z.array(RawHolding) });
export type HoldingsResponse = z.infer<typeof HoldingsResponse>;
/** `GET /api/portfolio/trades`. */
export const TradesResponse = z.object({ trades: z.array(RawTrade) });
export type TradesResponse = z.infer<typeof TradesResponse>;
/** `GET /api/portfolio/corporate-actions`. */
export const ActionsResponse = z.object({ actions: z.array(RawAction) });
export type ActionsResponse = z.infer<typeof ActionsResponse>;

const Month = z.string().regex(/^\d{4}-(0[1-9]|1[0-2])$/);
/** Owner-only: the monthly buy budget in rupees (a month's own figure, else `default`). */
export const BudgetBody = z.object({
  default: z.number().finite().min(0),
  months: z.record(Month, z.number().finite().min(0)).default({}),
});
export type BudgetBody = z.infer<typeof BudgetBody>;

/** Owner-only: target share of the whole per asset class (`money`'s `LABELS` keys); shares add to 1 within 1%. */
export const MixBody = z
  .object({
    mix: z.partialRecord(
      z.enum(["stocks", "equity_funds", "debt_funds", "gold", "foreign", "other_funds"]),
      z.number().min(0).max(1),
    ),
  })
  .refine((b) => Math.abs(Object.values(b.mix).reduce((a, x) => a + x, 0) - 1) <= 0.01, {
    message: "shares must add to 1",
  });
export type MixBody = z.infer<typeof MixBody>;

/** `GET /api/portfolio/settings` (owner only): both, null until set. */
export const SettingsResponse = z.object({
  budget: BudgetBody.nullable(),
  mix: z.partialRecord(z.string(), z.number()).nullable(),
});
export type SettingsResponse = z.infer<typeof SettingsResponse>;
