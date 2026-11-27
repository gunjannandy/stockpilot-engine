// C-061-1: the ITR pack equals the captured Python outputs.
import { describe, expect, it } from "vitest";
import { buildPack, packZip } from "../money/src/itr/itr";
import type { RateOn } from "../money/src/tax/tax";
import { captured } from "./captured";

// biome-ignore lint/suspicious/noExplicitAny: captured JSON
type Any = any;
const cases = captured<Any>("itr.json");
const rateOf =
  (table: Record<string, number>): RateOn =>
  (day) => {
    const ks = Object.keys(table).filter((k) => k <= day);
    return ks.length ? table[ks.sort().pop() as string] : null;
  };

/** Cells compare as numbers where both read as numbers: Python writes `100.0` where JS writes `100`. */
const cells = (text: string) =>
  text
    .split(/\r?\n/)
    .filter(Boolean)
    .map((l) => l.split(",").map((v) => (v !== "" && !Number.isNaN(Number(v)) ? Number(v) : v)));

describe("C-061-1 the ITR pack equals the captured Python outputs", () => {
  it("has captured cases", () => {
    expect(cases.length).toBeGreaterThan(15);
    expect(cases.filter((c) => c.output.files).length).toBeGreaterThan(10);
  });
  cases.forEach((c, i) => {
    it(`pack ${i}`, () => {
      const run = () =>
        buildPack({
          lots: c.lots,
          sales: c.sales,
          fy: c.fy,
          rateOn: rateOf(c.fx),
          closes: c.closes,
          fmv2018: c.fmv_2018,
          carried: c.carried,
          slabIncome: c.slab_income,
          fxNote: "test rates",
        });
      if (c.output.error) return expect(run).toThrow();
      const got = run();
      expect(got.itr_form).toBe(c.output.itr_form);
      const want = c.output.files as Record<string, string>;
      expect(Object.keys(got.files).sort()).toEqual(Object.keys(want).sort());
      expect(got.files["README.txt"]).toBe(want["README.txt"]);
      // JSON.stringify writes -0 as 0, which is how Python's "-0.0" reads back as a number
      const norm = (t: string) => JSON.parse(JSON.stringify(JSON.parse(t)));
      expect(norm(got.files["summary.json"] as string)).toEqual(
        norm(want["summary.json"] as string),
      );
      for (const f of ["gains_detail.csv", "schedule_112a.csv", "schedule_fa.csv"]) {
        expect(cells(got.files[f] as string)).toEqual(cells(want[f] as string));
      }
    });
  });
  it("downloads as one zip with the five files", () => {
    const c = cases.find((x) => x.output.files);
    const got = buildPack({
      lots: c.lots,
      sales: c.sales,
      fy: c.fy,
      rateOn: rateOf(c.fx),
      closes: c.closes,
      fmv2018: c.fmv_2018,
      carried: c.carried,
      slabIncome: c.slab_income,
    });
    const zip = packZip(got.files);
    expect([...zip.slice(0, 4)]).toEqual([0x50, 0x4b, 3, 4]);
    expect(new TextDecoder().decode(zip)).toContain("summary.json");
  });
});
