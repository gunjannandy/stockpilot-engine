import { describe, expect, it } from "vitest";
import { lakh, money, pct } from "./format";

describe("format", () => {
  it("writes rupees the Indian way", () => {
    expect(money(1234567)).toBe("₹12,34,567");
    expect(money(-50.5)).toBe("−₹50.5");
  });
  it("says lakh and crore in words", () => {
    expect(lakh(250000)).toBe("₹2.50 lakh");
    expect(lakh(31000000)).toBe("₹3.10 crore");
    expect(lakh(900)).toBe("₹900");
  });
  it("signs percents", () => {
    expect(pct(1.25)).toBe("+1.3%");
    expect(pct(-2, 0)).toBe("−2%");
  });
});
