// The day's call line: one pure function, so Today and the morning email say the same thing. "Nothing to do today" is
// a valid answer. A sell on something held comes first; then the best buy, when there is money left to spend.
export type CallInput = {
  symbol: string;
  verdict: string;
  chance: number | null;
  madeOn: string;
};

export type CallLine = {
  kind: "sell" | "buy" | "nothing";
  en: string;
  bn: string;
  /** The stocks the line is about, in order. */
  symbols: string[];
};

export type CallLineInput = {
  calls: readonly CallInput[];
  /** Symbols held (from the holdings). */
  held: ReadonlySet<string>;
  /** Rupees left to invest this month; null when no budget is set (a buy is then still shown). */
  moneyLeft: number | null;
  /** Symbols the owners set aside with Not now. */
  notNow?: ReadonlySet<string>;
};

const NOTHING: CallLine = {
  kind: "nothing",
  en: "Nothing to do today.",
  bn: "আজ কিছু করার নেই।",
  symbols: [],
};

const more = (n: number) =>
  n > 0 ? { en: ` and ${n} more`, bn: ` ও আরও ${n}টি` } : { en: "", bn: "" };

export function callLine(input: CallLineInput): CallLine {
  const hidden = input.notNow ?? new Set<string>();
  const live = input.calls.filter((c) => !hidden.has(c.symbol));
  const sells = live
    .filter((c) => c.verdict === "Sell" && input.held.has(c.symbol))
    .sort((a, b) => (a.chance ?? 1) - (b.chance ?? 1) || a.symbol.localeCompare(b.symbol));
  if (sells.length) {
    const m = more(sells.length - 1);
    const s = sells[0]?.symbol ?? "";
    return {
      kind: "sell",
      en: `Sell ${s}${m.en} today.`,
      bn: `আজ ${s}${m.bn} বিক্রি করুন।`,
      symbols: sells.map((c) => c.symbol),
    };
  }
  const canBuy = input.moneyLeft === null || input.moneyLeft > 0;
  const buys = live
    .filter((c) => c.verdict === "Buy" && c.chance !== null)
    .sort((a, b) => (b.chance ?? 0) - (a.chance ?? 0) || a.symbol.localeCompare(b.symbol));
  if (canBuy && buys.length) {
    const top = buys[0];
    const m = more(buys.length - 1);
    const pct = Math.round((top?.chance ?? 0) * 100);
    return {
      kind: "buy",
      en: `Consider buying ${top?.symbol}${m.en}: a ${pct} in 100 chance of beating the Nifty.`,
      bn: `${top?.symbol}${m.bn} কেনার কথা ভাবুন: নিফটিকে হারানোর সম্ভাবনা ১০০-তে ${pct}।`,
      symbols: buys.map((c) => c.symbol),
    };
  }
  return NOTHING;
}
