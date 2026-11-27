// News exposure per holding: direction × size × position. Reads only per-stock impact rows
// (never a sector tag): a row whose relation is "sector" has no direction and is skipped.
export type Impact = {
  symbol: string;
  relation: "self" | "rival" | "supplier" | "customer" | "sector";
  direction: "up" | "down" | "flat";
  size: "small" | "medium" | "large";
};

/** The move in the stock's price a size stands for (fractions). */
export const SIZE_MOVE = { small: 0.01, medium: 0.03, large: 0.06 } as const;

export type HoldingValue = { symbol: string; value: number };
export type ExposureRow = {
  symbol: string;
  share: number;
  netMove: number;
  changeInr: number;
  impacts: number;
};

/** Per holding: the sum of direction × size over its impact rows, applied to its value.
 *  Sorted by the size of the rupee change, biggest first; holdings with no impact are left out. */
export function newsExposure(
  holdings: readonly HoldingValue[],
  impacts: readonly Impact[],
): ExposureRow[] {
  const total = holdings.reduce((s, h) => s + Math.max(h.value, 0), 0);
  const net = new Map<string, { move: number; n: number }>();
  for (const i of impacts) {
    if (i.relation === "sector" || i.direction === "flat") continue;
    const sign = i.direction === "up" ? 1 : -1;
    const cur = net.get(i.symbol) ?? { move: 0, n: 0 };
    cur.move += sign * SIZE_MOVE[i.size];
    cur.n += 1;
    net.set(i.symbol, cur);
  }
  const rows: ExposureRow[] = [];
  for (const h of holdings) {
    const e = net.get(h.symbol);
    if (!e || !(h.value > 0)) continue;
    rows.push({
      symbol: h.symbol,
      share: total ? h.value / total : 0,
      netMove: e.move,
      changeInr: h.value * e.move,
      impacts: e.n,
    });
  }
  return rows.sort(
    (a, b) => Math.abs(b.changeInr) - Math.abs(a.changeInr) || (a.symbol < b.symbol ? -1 : 1),
  );
}
