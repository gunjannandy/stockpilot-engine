// C-020-1: each pane answer carries its dataset's updated time.

import { describe, expect, it } from "vitest";
import { DatasetAnswer, datasets } from "../contract/src/index";

describe("C-020-1 freshness on every pane answer", () => {
  it("the dataset answer has the run's as-of and published time", () => {
    const keys = Object.keys(DatasetAnswer.shape);
    expect(keys).toContain("as_of");
    expect(keys).toContain("published_at");
  });
  it("every dataset has a freshness window the chip can compare against", () => {
    for (const d of Object.values(datasets)) expect(d.freshnessHours).toBeGreaterThan(0);
  });
});
