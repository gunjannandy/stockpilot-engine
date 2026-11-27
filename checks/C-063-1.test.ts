// C-063-1: XIRR against hand-worked fixtures.
import { expect, it } from "vitest";
import { returnVsNifty, xirr } from "../money/src/xirr/xirr";

it("C-063-1 one year, 100 in and 110 out is 10%", () => {
  expect(
    xirr([
      { day: "2025-01-01", amount: -100 },
      { day: "2026-01-01", amount: 110 },
    ]),
  ).toBeCloseTo(0.1, 6);
});
it("C-063-1 two years, 100 to 121 is 10% a year (730 days)", () => {
  expect(
    xirr([
      { day: "2024-01-01", amount: -100 },
      { day: "2025-12-31", amount: 121 },
    ]),
  ).toBeCloseTo(0.1, 4);
});
it("C-063-1 two buys then today's value", () => {
  // -100 at t0, -100 at +1y, 231 at +2y(730d): 100(1+r)^2 + 100(1+r) = 231 -> r = 0.1
  const r = xirr([
    { day: "2024-01-01", amount: -100 },
    { day: "2024-12-31", amount: -100 },
    { day: "2025-12-31", amount: 231 },
  ]);
  expect(r).toBeCloseTo(0.1, 3);
});
it("C-063-1 no sign change has no answer; a loss is negative", () => {
  expect(xirr([{ day: "2025-01-01", amount: -100 }])).toBeNull();
  expect(
    xirr([
      { day: "2025-01-01", amount: -100 },
      { day: "2026-01-01", amount: 90 },
    ]),
  ).toBeCloseTo(-0.1, 6);
});
it("C-063-1 against the Nifty over the same flows", () => {
  const nifty = (d: string) => (d === "2025-01-01" ? 20000 : 22000); // +10%
  const r = returnVsNifty([{ day: "2025-01-01", amount: -100 }], 130, "2026-01-01", nifty);
  expect(r.holding).toBeCloseTo(0.3, 6);
  expect(r.nifty).toBeCloseTo(0.1, 6);
  expect(r.edge).toBeCloseTo(0.2, 6);
  expect(
    returnVsNifty([{ day: "2025-01-01", amount: -100 }], 130, "2026-01-01", () => null).nifty,
  ).toBeNull();
});
