import { z } from "zod";

/** One realised sale matched to the lot it came from (a row of the tax pack). Amounts are rupees. */
export const GainRow = z.object({
  symbol: z.string(),
  bucket: z.string(),
  acquired_on: z.string(),
  sold_on: z.string(),
  quantity: z.number(),
  cost: z.number(),
  proceeds: z.number(),
  expenses: z.number(),
  gain: z.number(),
  term: z.string(),
  grandfathered: z.boolean(),
});
export type GainRow = z.infer<typeof GainRow>;

/** `GET /api/money/tax?fy=2026` (2026-27): gains booked in that tax year, netted by pool, with the tax they
 * come to. `harvest` is sized from the newest stored closes. */
export const TaxResponse = z.object({
  fy: z.number().int(),
  label: z.string(),
  rows: z.array(GainRow),
  net: z.object({
    stcg_slab: z.number(),
    stcg_equity: z.number(),
    ltcg_other: z.number(),
    ltcg_equity: z.number(),
    carry_forward: z.object({ stcl: z.number(), ltcl: z.number() }),
  }),
  tax: z.object({ total: z.number(), surcharge: z.number(), cess: z.number() }),
  ltcg_equity_exempt: z.number(),
  ltcg_equity_room_left: z.number(),
  harvest: z.object({
    gain_room: z.number(),
    gain_candidates: z.array(
      z.object({
        symbol: z.string(),
        quantity: z.number(),
        gain: z.number(),
        future_tax_saved: z.number(),
      }),
    ),
    gain_room_left: z.number(),
    loss_candidates: z.array(
      z.object({ symbol: z.string(), quantity: z.number(), loss: z.number() }),
    ),
  }),
  warnings: z.array(z.string()),
});
export type TaxResponse = z.infer<typeof TaxResponse>;

/** `GET /api/money/xirr`: the yearly return of the stock trades, whole and per stock, against the Nifty over
 * the same cash flows. Each value is a fraction (0.12 is 12%) or null when it cannot be worked out. */
export const XirrResponse = z.object({
  as_of: z.string().nullable(),
  portfolio: z.object({
    xirr: z.number().nullable(),
    nifty: z.number().nullable(),
    edge: z.number().nullable(),
  }),
  holdings: z.array(
    z.object({
      symbol: z.string(),
      quantity: z.number(),
      value: z.number().nullable(),
      xirr: z.number().nullable(),
    }),
  ),
  warnings: z.array(z.string()),
});
export type XirrResponse = z.infer<typeof XirrResponse>;

const Slice = z.object({ key: z.string(), value: z.number(), share: z.number() });

/** `GET /api/money/risk`: how the held stocks split by stock and sector, which pass their limits, and what a
 * Nifty fall would do. Sector and beta are not stored yet: sectors read "Unknown" and every beta counts as 1. */
export const RiskResponse = z.object({
  concentration: z.object({
    total: z.number(),
    byStock: z.array(Slice),
    bySector: z.array(Slice),
    flags: z.array(
      z.object({ kind: z.enum(["stock", "sector"]), key: z.string(), share: z.number() }),
    ),
  }),
  shock: z.object({
    fall: z.number(),
    total: z.number(),
    lossInr: z.number(),
    lossShare: z.number(),
    perStock: z.array(z.object({ symbol: z.string(), move: z.number(), changeInr: z.number() })),
    assumedBeta: z.array(z.string()),
  }),
  warnings: z.array(z.string()),
});
export type RiskResponse = z.infer<typeof RiskResponse>;
