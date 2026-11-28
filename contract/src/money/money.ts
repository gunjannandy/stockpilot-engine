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

/** `POST /api/money/us-prices` (the usprices Job): newest closes of US shares, one symbol a call. */
export const UsPricesPost = z.object({
  symbol: z.string().min(1),
  rows: z
    .array(
      z.object({ date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/), close: z.number().positive() }),
    )
    .max(5000),
});
export type UsPricesPost = z.infer<typeof UsPricesPost>;

/** `GET /api/money/rsu`: the dollar holding valued at the newest stored close and USD/INR, with the tax if all
 * of it were sold that day, and the vests expected next. `value` is null until a price and a rate are stored. */
export const RsuResponse = z.object({
  as_of: z.string().nullable(),
  symbols: z.array(
    z.object({
      symbol: z.string(),
      priceUsd: z.number().nullable(),
      priceDate: z.string().nullable(),
      view: z
        .object({
          shares: z.number(),
          valueInr: z.number(),
          gainInr: z.number(),
          taxInr: z.number(),
          estimatedShares: z.number(),
          lots: z.array(
            z.object({
              acquiredOn: z.string(),
              quantity: z.number(),
              valueInr: z.number(),
              gainInr: z.number(),
              taxInr: z.number(),
              estimated: z.boolean(),
            }),
          ),
        })
        .nullable(),
      expectedVests: z.array(z.object({ day: z.string(), quantity: z.number() })),
    }),
  ),
  usdInr: z.number().nullable(),
  warnings: z.array(z.string()),
});
export type RsuResponse = z.infer<typeof RsuResponse>;

/** One row a day for the `usprices` dataset: what the daily run did. The closes go to `POST /api/money/us-prices`. */
export const UsPricesRun = z.object({
  id: z.string().min(1),
  day: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  symbols: z.number().int().min(0),
  rows: z.number().int().min(0),
  held_back: z.number().int().min(0),
});
export type UsPricesRun = z.infer<typeof UsPricesRun>;

/** `GET /api/money/us-symbols` (the usprices Job): the dollar stocks still held and the day to load from. */
export const UsSymbols = z.object({
  symbols: z.array(z.string()),
  since: z.string(),
  fx_since: z.string(),
});
export type UsSymbols = z.infer<typeof UsSymbols>;

/** `GET /api/money/calendar`: what is coming for the stocks held. `actions` are dated splits, bonuses, symbol
 * changes and delistings; `dividends` are expected: each past ex-date of the last year, one year on, times the shares held. */
export const CalendarResponse = z.object({
  as_of: z.string(),
  actions: z.array(
    z.object({
      date: z.string(),
      kind: z.string(),
      symbol: z.string(),
      detail: z.string().nullable(),
    }),
  ),
  dividends: z.array(
    z.object({
      date: z.string(),
      symbol: z.string(),
      perShare: z.number(),
      shares: z.number(),
      cash: z.number(),
    }),
  ),
  expectedCash: z.number(),
  warnings: z.array(z.string()),
});
export type CalendarResponse = z.infer<typeof CalendarResponse>;

/** `POST /api/money/dividends` (the dividends Job): cash dividends per share by ex-date, one symbol a call. */
export const DividendsPost = z.object({
  symbol: z.string().min(1),
  rows: z
    .array(
      z.object({
        ex_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
        per_share: z.number().positive(),
      }),
    )
    .max(2000),
});
export type DividendsPost = z.infer<typeof DividendsPost>;

/** `GET /api/money/held-symbols` (the dividends Job): INR stocks still held. */
export const HeldSymbols = z.object({ symbols: z.array(z.string()), since: z.string() });
export type HeldSymbols = z.infer<typeof HeldSymbols>;

/** One row a day for the `dividends` dataset. */
export const DividendsRun = z.object({
  id: z.string().min(1),
  day: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  symbols: z.number().int().min(0),
  rows: z.number().int().min(0),
});
export type DividendsRun = z.infer<typeof DividendsRun>;
