import { z } from "zod";

/** Whose a row is and where it came from: both are required on every holding and trade, so a second
 * account later is data, not a migration (story 68). */
const Whose = {
  account: z.string().min(1),
  source: z.string().min(1),
};

/** One raw holding as a sync stores it. `snapshot_at` is the sync's time. */
export const RawHolding = z.object({
  ...Whose,
  snapshot_at: z.string().min(1),
  kind: z.enum(["stock", "mf", "rsu"]),
  symbol: z.string().min(1),
  isin: z.string().nullable(),
  quantity: z.number(),
  avg_price: z.number(),
});
export type RawHolding = z.infer<typeof RawHolding>;

/** One raw executed trade. `trade_key` is the exchange trade id. */
export const RawTrade = z.object({
  ...Whose,
  trade_key: z.string().min(1),
  source_ref: z.string(),
  kind: z.enum(["stock", "mf", "rsu"]),
  symbol: z.string().min(1),
  isin: z.string().nullable(),
  side: z.enum(["buy", "sell", "vest", "credit", "debit"]),
  trade_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  quantity: z.number(),
  price: z.number().nullable(),
});
export type RawTrade = z.infer<typeof RawTrade>;

/** The steps of a Sync, in order; the pane words each one in English and Bengali. */
export const SYNC_STEPS = ["login", "holdings", "trades", "done"] as const;
export const SyncStep = z.object({
  id: z.enum(SYNC_STEPS),
  state: z.enum(["ok", "fail"]),
  count: z.number().int().min(0).nullable(),
});
export const SyncStatus = z.object({
  synced_at: z.string().nullable(),
  changes: z.number().int().min(0).nullable(),
  steps: z.array(SyncStep),
});
export type SyncStatus = z.infer<typeof SyncStatus>;

/** What the Refresh button answers. */
export const RefreshResponse = z.object({
  key: z.string(),
  status: z.literal("queued"),
});
