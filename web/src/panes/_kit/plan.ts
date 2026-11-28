// The owner's plan, shared by Portfolio (read) and Settings (change): monthly budget, money left, target mix. Made-up numbers.
export const BUDGET = 200000;
export const MONEY_LEFT = 184000;
export const TARGET: Record<string, number> = {
  Banks: 20,
  IT: 15,
  Health: 10,
  Consumer: 12,
  Energy: 10,
  Auto: 8,
  Metals: 5,
  Transport: 5,
  Materials: 5,
  Retail: 4,
  Telecom: 3,
  Finance: 3,
};

/** Rupees spent on stock and fund buys in a calendar month ("YYYY-MM"), from the stored trades. */
export function spentIn(
  trades: {
    kind: string;
    side: string;
    trade_date: string;
    quantity: number;
    price: number | null;
  }[],
  month: string,
): number {
  let sum = 0;
  for (const t of trades)
    if (t.side === "buy" && t.kind !== "rsu" && t.trade_date.startsWith(month))
      sum += t.quantity * (t.price ?? 0);
  return sum;
}

/** The month's budget: its own figure, else the default. */
export function budgetFor(
  b: { default: number; months: Record<string, number> } | null | undefined,
  month: string,
): number | null {
  return b ? (b.months[month] ?? b.default) : null;
}

/** Today's month in India ("YYYY-MM"), whatever the machine's clock zone. */
export function istMonth(now = new Date()): string {
  return new Date(now.getTime() + 330 * 60000).toISOString().slice(0, 7);
}
