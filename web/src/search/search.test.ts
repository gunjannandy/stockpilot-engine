import { describe, expect, it } from "vitest";
import { createSearch } from "./core";
import fixture from "./fixture-index.json";

describe("search", () => {
  const s = createSearch(fixture);
  it("finds a stock by a fuzzy name", () => {
    expect(s.find("textils")[0]?.symbol).toBe("ARANYA");
    expect(s.find("mitra soft")[0]?.symbol).toBe("MITRA");
  });
  it("puts an exact symbol first, and finds nothing for nonsense", () => {
    expect(s.find("tarang")[0]?.symbol).toBe("TARANG");
    expect(s.find("zzzzqq")).toEqual([]);
  });
});
