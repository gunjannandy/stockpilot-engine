// C-009-1: the build fails on any fixed word without Bengali.
import { expect, it } from "vitest";
import { assertWordsComplete } from "../web/src/words/core";

it("C-009-1 a fixed word without Bengali fails the build", () => {
  expect(() => assertWordsComplete({ "a.en": { k: "Sell" }, "a.bn": { k: "" } })).toThrow(/a\.k/);
  expect(() =>
    assertWordsComplete({ "a.en": { k: "Sell" }, "a.bn": { k: "বিক্রি (Sell)" } }),
  ).not.toThrow();
});
