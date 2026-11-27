// Allocation against the target mix the owners approved, by asset class, in rupees.
// A port of Python `analysis/allocation.py`.
import { pyFixed } from "../core/round";

export const LABELS: Record<string, string> = {
  stocks: "Indian stocks",
  equity_funds: "Equity funds",
  debt_funds: "Debt funds",
  gold: "Gold",
  foreign: "US shares (RSUs)",
  other_funds: "Other funds",
};
export const CLOSE_ENOUGH = 0.02; // within 2% of the total is "on target"

export function assetClass(h: { kind: string; category: string | null }): string {
  if (h.kind === "equity") return "stocks";
  if (h.kind === "foreign") return "foreign";
  const c = (h.category ?? "").toLowerCase();
  if (c.startsWith("equity scheme") || c.includes("arbitrage") || c.includes("aggressive"))
    return "equity_funds";
  if (c.startsWith("debt scheme")) return "debt_funds";
  if (c.includes("gold")) return "gold";
  return "other_funds";
}

export type AllocPosition = {
  symbol: string;
  kind: string;
  category: string | null;
  quantity: number;
  price: number | null;
};
export type AllocRow = {
  class: string;
  label: string;
  value: number;
  share: number;
  target: number | null;
  gapInr: number | null;
  action: string;
};
export type Allocation = {
  total: number;
  targetSet: boolean;
  rows: AllocRow[];
  unpriced: string[];
};

/** Python's `f"{n:,.0f}"`. */
function inr0(n: number): string {
  return pyFixed(n, 0).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

export function compare(
  positions: readonly AllocPosition[],
  target: Record<string, number> | null,
): Allocation {
  const values = new Map<string, number>();
  const unpriced: string[] = [];
  for (const p of positions) {
    if (p.price === null) {
      unpriced.push(p.symbol);
      continue;
    }
    const cls = assetClass(p);
    values.set(cls, (values.get(cls) ?? 0) + p.quantity * p.price);
  }
  let total = 0;
  for (const v of values.values()) total += v;
  const classes = [...new Set([...values.keys(), ...Object.keys(target ?? {})])].sort(
    (a, b) => (values.get(b) ?? 0) - (values.get(a) ?? 0),
  );
  const rows = classes.map((cls): AllocRow => {
    const value = values.get(cls) ?? 0;
    const row: AllocRow = {
      class: cls,
      label: LABELS[cls] ?? cls,
      value,
      share: total ? value / total : 0,
      target: null,
      gapInr: null,
      action: "",
    };
    if (target) {
      row.target = target[cls] ?? 0;
      row.gapInr = row.target * total - value;
      const gap = row.gapInr;
      row.action =
        Math.abs(gap) <= CLOSE_ENOUGH * total
          ? "On target"
          : `${gap > 0 ? "Add" : "Trim"} ₹${inr0(Math.abs(gap))}`;
    }
    return row;
  });
  return { total, targetSet: Boolean(target), rows, unpriced };
}
