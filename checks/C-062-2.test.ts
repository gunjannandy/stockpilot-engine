// Allocation against the target mix (port of the Python rows).
import { expect, it } from "vitest";
import { compare } from "../money/src/budget/allocation";

it("allocation: gaps and actions against the target", () => {
  const a = compare(
    [
      { symbol: "A", kind: "equity", category: null, quantity: 10, price: 60 },
      { symbol: "F", kind: "mf", category: "Debt Scheme - Liquid Fund", quantity: 10, price: 30 },
      { symbol: "G", kind: "mf", category: "Other Scheme - Gold ETF", quantity: 1, price: 10 },
      { symbol: "X", kind: "equity", category: null, quantity: 1, price: null },
    ],
    { stocks: 0.5, debt_funds: 0.3, gold: 0.2 },
  );
  expect(a.total).toBe(910);
  expect(a.unpriced).toEqual(["X"]);
  const by = Object.fromEntries(a.rows.map((r) => [r.class, r]));
  expect(by.stocks?.action).toBe("Trim ₹145");
  expect(by.debt_funds?.action).toBe("Trim ₹27");
  expect(by.gold?.action).toBe("Add ₹172");
  expect(compare([], null).rows).toEqual([]);
});
