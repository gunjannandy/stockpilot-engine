import { index, integer, real, sqliteTable, text } from "drizzle-orm/sqlite-core";

/** Append-only: the Worker only inserts (checks/C-035-1 scans for any update or delete). */
export const calls = sqliteTable(
  "calls",
  {
    id: text("id").primaryKey(),
    symbol: text("symbol").notNull(),
    exchange: text("exchange").notNull(),
    madeOn: text("made_on").notNull(),
    verdict: text("verdict").notNull(),
    chance: real("chance"),
    horizonDays: integer("horizon_days").notNull(),
    baseCases: integer("base_cases").notNull(),
    baseRate: real("base_rate"),
    sellLine: real("sell_line").notNull(),
    buyLine: real("buy_line").notNull(),
    couldRiseTo: real("could_rise_to"),
    wouldBuyAt: real("would_buy_at"),
    sellAtOnceAt: real("sell_at_once_at"),
    limited: integer("limited").notNull(),
    sentencesJson: text("sentences_json").notNull(),
    similarN: integer("similar_n").notNull(),
    similarBeat: integer("similar_beat").notNull(),
    modelVersion: text("model_version").notNull(),
  },
  (t) => [index("calls_symbol").on(t.symbol, t.madeOn), index("calls_day").on(t.madeOn)],
);

/** One row per scored call: whether it beat the Nifty. Written by the scoring Job. */
export const callScores = sqliteTable("call_scores", {
  callId: text("call_id").primaryKey(),
  beat: integer("beat").notNull(),
  scoredOn: text("scored_on").notNull(),
  stockRet: real("stock_ret"),
  niftyRet: real("nifty_ret"),
  equalRet: real("equal_ret"),
});
