// Shared number formatters for every screen: rupees, lakh and crore in words, signed percent.
// Money here is only for showing; the sums themselves live in the money package and the API.
export const RS = "₹";
export const money = (v: number, dp = v < 1000 ? 1 : 0) =>
  `${v < 0 ? "−" : ""}${RS}${Math.abs(v).toLocaleString("en-IN", { maximumFractionDigits: dp })}`;
export const lakh = (v: number) =>
  Math.abs(v) >= 1e7
    ? `${RS}${(v / 1e7).toFixed(2)} crore`
    : Math.abs(v) >= 1e5
      ? `${RS}${(v / 1e5).toFixed(2)} lakh`
      : money(v);
export const pct = (v: number, dp = 1) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(dp)}%`;
