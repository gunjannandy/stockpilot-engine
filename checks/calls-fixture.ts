// Shared fixture for the calls checks: one valid call row, with overrides.
export const sentences = (extra: { key: string; en: string; bn: string }[] = []) =>
  JSON.stringify([
    {
      key: "why_buy",
      en: "Our model gives it a 62 in 100 chance.",
      bn: "আমাদের মডেল ১০০-তে ৬২ সম্ভাবনা দিচ্ছে।",
    },
    ...extra,
  ]);

export const callBase = (over: Record<string, unknown> = {}) => ({
  id: "NSE:ABC:2026-11-28:63",
  symbol: "ABC",
  exchange: "NSE",
  made_on: "2026-11-28",
  verdict: "Buy",
  chance: 0.62,
  horizon_days: 63,
  base_cases: 400,
  base_rate: 0.5,
  sell_line: 0.4,
  buy_line: 0.57,
  could_rise_to: 130,
  would_buy_at: null,
  sell_at_once_at: 90,
  limited: false,
  sentences_json: sentences(),
  similar_n: 24,
  similar_beat: 15,
  model_version: "mech-v1",
  ...over,
});
