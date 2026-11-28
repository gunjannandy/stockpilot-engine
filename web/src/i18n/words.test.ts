// C-009-1: the build fails on any fixed word without Bengali. This runs over every real words file.
import { describe, expect, it } from "vitest";
import { assertWordsComplete, missingBengali, type WordFiles } from "../words/core";

describe("word table", () => {
  it("flags a fixed word with no Bengali", () => {
    expect(missingBengali({ a: "A", b: "B" }, { a: "ক", b: " " })).toEqual(["b"]);
    expect(() => assertWordsComplete({ "x.en": { a: "A" }, "x.bn": {} })).toThrow(/x\.a/);
  });
  it("every shipped words file has Bengali for every English word", () => {
    const mods = import.meta.glob("../words/*.json", { eager: true }) as Record<
      string,
      { default: Record<string, string> }
    >;
    const files: WordFiles = {};
    for (const [f, m] of Object.entries(mods))
      files[(f.split("/").pop() ?? "").replace(".json", "")] = m.default;
    expect(() => assertWordsComplete(files)).not.toThrow();
  });
});
