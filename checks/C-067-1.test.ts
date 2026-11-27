// C-067-1: tax rules are picked by date from the one data file.
import { expect, it } from "vitest";
import rulesFile from "../money/rules/tax-rules.json";
import { rulesFor, rulesOn, type TaxRules } from "../money/src/tax/tax";

it("C-067-1 the 1961 Act before tax year 2026-27, the 2025 Act from it", () => {
  expect(rulesOn("2025-03-31").act).toBe("1961");
  expect(rulesOn("2026-03-31").act).toBe("1961");
  expect(rulesOn("2026-04-01").act).toBe("2025");
  expect(rulesFor(2030).act).toBe("2025");
  expect(rulesFor(2026).ltcg_exempt).toBe(125000);
});
it("C-067-1 before the first dated set there is no answer", () => {
  expect(() => rulesFor(2023)).toThrow(/no rule set/);
});
it("C-067-1 a new dated entry in the data takes over from its year, nothing in code changes", () => {
  const sets = [
    ...(rulesFile.sets as TaxRules[]),
    { ...(rulesFile.sets[1] as TaxRules), act: "next", from_fy: 2028, ltcg_exempt: 200000 },
  ];
  expect(rulesFor(2027, sets).ltcg_exempt).toBe(125000);
  expect(rulesFor(2028, sets).ltcg_exempt).toBe(200000);
});
