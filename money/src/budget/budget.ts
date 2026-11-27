// Money left this month: the budget the owners set, minus what this month's buys cost.
import { type Day, month } from "../core/dates";

export type Buy = { day: Day; quantity: number; price: number; side?: string };

/** The budget for the month of `day`: the owners' figure for that month, else the default. */
export function budgetFor(budgets: Record<string, number>, day: Day, fallback: number): number {
  const v = budgets[month(day)];
  return v === undefined ? fallback : v;
}

/** Rupees spent on buys in `day`'s calendar month (sells and other months do not count). */
export function spentInMonth(buys: readonly Buy[], day: Day): number {
  let total = 0;
  for (const b of buys) {
    if ((b.side ?? "buy") === "buy" && month(b.day) === month(day)) total += b.quantity * b.price;
  }
  return total;
}

/** Budget minus this month's buys. Negative means over budget; the caller words that. */
export function moneyLeft(budget: number, buys: readonly Buy[], day: Day): number {
  return budget - spentInMonth(buys, day);
}
