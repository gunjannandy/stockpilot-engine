// C-086-1: news exposure = direction x size x position, from per-stock impact rows only.
import { expect, it } from "vitest";
import { newsExposure } from "../money/src/exposure/exposure";

it("C-086-1 exposure arithmetic", () => {
  const rows = newsExposure(
    [
      { symbol: "AAA", value: 1000 },
      { symbol: "BBB", value: 3000 },
      { symbol: "CCC", value: 500 },
    ],
    [
      { symbol: "AAA", relation: "self", direction: "down", size: "large" },
      { symbol: "AAA", relation: "rival", direction: "up", size: "small" },
      { symbol: "BBB", relation: "customer", direction: "up", size: "medium" },
      { symbol: "CCC", relation: "sector", direction: "down", size: "large" },
      { symbol: "BBB", relation: "self", direction: "flat", size: "large" },
    ],
  );
  expect(rows.map((r) => r.symbol)).toEqual(["BBB", "AAA"]); // CCC: sector tag has no direction
  expect(rows[0]?.changeInr).toBeCloseTo(90, 9);
  expect(rows[1]?.netMove).toBeCloseTo(-0.05, 9);
  expect(rows[1]?.changeInr).toBeCloseTo(-50, 9);
  expect(rows[1]?.share).toBeCloseTo(1000 / 4500, 9);
});
