// C-062-1: RSU value and tax; C-062-4: a gap to the current share count is one estimated lot.
import { expect, it } from "vitest";
import { expectedVests, rsuView, vestsFromPayslips, withEstimatedGap } from "../money/src/rsu/rsu";

const rule = { longTermDays: 730, shortRate: 0.3, longRate: 0.125 };

it("C-062-1 value and tax per lot, cost at the vest-day rate", () => {
  const v = rsuView({
    lots: [
      { acquiredOn: "2023-01-10", quantity: 10, costUsd: 100 },
      { acquiredOn: "2026-06-10", quantity: 5, costUsd: 200 },
    ],
    priceUsd: 150,
    rate: 90,
    rateOn: (d) => (d < "2024-01-01" ? 80 : 85),
    rule,
    asOf: "2026-11-25",
  });
  expect(v.shares).toBe(15);
  expect(v.valueInr).toBe(15 * 150 * 90);
  const l0 = 10 * 150 * 90 - 10 * 100 * 80; // 55000, long term
  const l1 = 5 * 150 * 90 - 5 * 200 * 85; // -17500, loss pays no tax
  expect(v.gainInr).toBe(l0 + l1);
  expect(v.taxInr).toBeCloseTo(l0 * 0.125, 6);
  expect(v.lots[1]?.taxInr).toBe(0);
});

it("C-062-1 expected vests: one per quarter, scaled by a split", () => {
  const out = expectedVests(
    [{ day: "2025-09-15", quantity: 10, priceUsd: 1, status: "confirmed" }],
    "2026-09-30",
    [{ exDate: "2025-12-18", numerator: 5, denominator: 1 }],
  );
  expect(out.map((v) => v.day)).toEqual(["2025-12-15", "2026-03-15", "2026-06-15", "2026-09-15"]);
  expect(out.map((v) => v.quantity)).toEqual([10, 50, 50, 50]);
  expect(
    vestsFromPayslips(
      [
        ["2026-03", 90000],
        ["2026-02", 0],
      ],
      () => 9000,
    ),
  ).toEqual([{ day: "2026-03-15", quantity: 10, priceUsd: null, status: "expected" }]);
});

it("C-062-4 a gap to the current share count is one estimated lot", () => {
  const lots = [{ acquiredOn: "2025-01-01", quantity: 10, costUsd: 100 }];
  const out = withEstimatedGap(lots, 14, "2026-11-25", 150);
  expect(out).toHaveLength(2);
  expect(out[1]).toEqual({ acquiredOn: "2026-11-25", quantity: 4, costUsd: 150, estimated: true });
  expect(withEstimatedGap(lots, 10, "2026-11-25", 150)).toEqual(lots);
  expect(withEstimatedGap(lots, 8, "2026-11-25", 150)).toEqual(lots);
});
