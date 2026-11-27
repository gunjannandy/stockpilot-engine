// C-026-1: money left equals the budget minus this month's buys.
import { expect, it } from "vitest";
import { budgetFor, moneyLeft } from "../money/src/budget/budget";

it("C-026-1 money left is the budget minus this month's buys", () => {
  const buys = [
    { day: "2026-11-03", quantity: 10, price: 250 },
    { day: "2026-11-20", quantity: 2, price: 1500.5 },
    { day: "2026-11-21", quantity: 5, price: 100, side: "sell" },
    { day: "2026-10-30", quantity: 100, price: 100 },
  ];
  expect(moneyLeft(50000, buys, "2026-11-25")).toBe(50000 - 2500 - 3001);
  expect(budgetFor({ "2026-11": 40000 }, "2026-11-25", 30000)).toBe(40000);
  expect(budgetFor({ "2026-11": 40000 }, "2026-12-01", 30000)).toBe(30000);
  expect(moneyLeft(1000, [], "2026-11-25")).toBe(1000);
});
