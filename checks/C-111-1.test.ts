// C-111-1: every dataset in the registry has a producer, schedule, freshness promise and checks.

import { describe, expect, it } from "vitest";
import { publishApp } from "../api/src/publish/testkit";
import { JobKind } from "../contract/src/core/jobs";
import { datasets } from "../contract/src/datasets";

describe("C-111-1 dataset registry", () => {
  it("names a producer, table or file, schedule, freshness promise, checks, recompute flag and write budget for every dataset", () => {
    for (const [key, ds] of Object.entries(datasets) as [
      string,
      (typeof datasets)[keyof typeof datasets],
    ][]) {
      expect(ds.name, key).toBe(key);
      expect(JobKind.safeParse(ds.job).success, `${key} producer`).toBe(true);
      expect(ds.table, `${key} table`).toMatch(/^[a-z][a-z0-9_]*$/);
      expect(ds.schedule.trim().length, `${key} schedule`).toBeGreaterThan(0);
      expect(ds.freshnessHours, `${key} freshness`).toBeGreaterThan(0);
      expect(ds.checks.row.length + ds.checks.run.length, `${key} checks`).toBeGreaterThan(0);
      expect(typeof ds.recomputable, `${key} recompute`).toBe("boolean");
      expect(ds.writeBudget, `${key} write budget`).toBeGreaterThan(0);
      expect(typeof ds.row.safeParse, `${key} row schema`).toBe("function");
    }
  });
  it("the door serves only registered datasets", async () => {
    const t = await publishApp();
    const res = await t.rows("not_registered", "a", [{ id: "x", n: 1 }]);
    expect(res.status).toBe(403);
  });
});
