// Pure helpers for stock rows: no data in them.

/** Where each "Open in" link points: the instrument itself, never a search page. */
export function openLinks(st: { symbol: string; exchange: "NSE" | "BSE" }) {
  return {
    kite: `https://kite.zerodha.com/chart/ext/tvc/${st.exchange}/${encodeURIComponent(st.symbol)}/0`,
    screener: `https://www.screener.in/company/${encodeURIComponent(st.symbol)}/`,
  };
}

/** The small coloured line each list row carries. */
export function sparkPath(closes: number[]) {
  const lo = Math.min(...closes);
  const hi = Math.max(...closes);
  const W = 100;
  const H = 30;
  const x = (i: number) => 2 + ((W - 4) * i) / (closes.length - 1);
  const y = (v: number) => 3 + (H - 6) * (1 - (v - lo) / (hi - lo || 1));
  const p = closes.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join("");
  return {
    line: p,
    area: `${p}L${x(closes.length - 1)} ${H}L${x(0)} ${H}Z`,
    up: (closes[closes.length - 1] ?? 0) >= (closes[0] ?? 0),
  };
}
