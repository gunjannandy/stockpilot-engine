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
 * come to. `harvest` is filled once prices are supplied by the US price Job (null until then). */
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
  warnings: z.array(z.string()),
});
export type TaxResponse = z.infer<typeof TaxResponse>;
