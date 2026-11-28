// C-203-1: every dataset states its visibility; one that looks like holdings, trades, tax, funds or
// feedback must be private, so a later dataset cannot forget it.
import { describe, expect, it } from "vitest";
import { datasets } from "../contract/src/datasets";

const SENSITIVE =
  /holding|trade|order|tax|fund|portfolio|position|feedback|pan\b|isin|pnl|contract_note/i;

describe("C-203-1 dataset visibility", () => {
  const all = Object.values(datasets) as {
    name: string;
    table: string;
    visibility?: string;
  }[];
  it("every dataset sets visibility explicitly", () => {
    const missing = all.filter((d) => d.visibility !== "public" && d.visibility !== "private");
    expect(missing.map((d) => d.name)).toEqual([]);
  });
  it("datasets named like holdings, trades, tax or feedback are private", () => {
    const leaks = all.filter(
      (d) => (SENSITIVE.test(d.name) || SENSITIVE.test(d.table)) && d.visibility !== "private",
    );
    expect(leaks.map((d) => d.name)).toEqual([]);
  });
});
