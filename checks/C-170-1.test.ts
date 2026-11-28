// C-170-1: a call outside 5% to 95%, without a base rate of 30 cases or a horizon is held back; a thin or moved
// bucket adds "limited evidence"; the screen is deterministic (its half is checks/C-170-2.py).

import { describe, expect, it } from "vitest";
import { makeApp } from "../api/src/testkit";
import { bucketLimited, callRowCheck } from "../contract/src/index";
import { callBase, sentences } from "./calls-fixture";

describe("C-170-1 a bad call never publishes", () => {
  it("holds back a chance outside 5% to 95%, a thin base rate, and a missing horizon", () => {
    expect(callRowCheck(callBase())).toBeNull();
    expect(callRowCheck(callBase({ chance: 0.97 }))).toMatch(/5% to 95%/);
    expect(callRowCheck(callBase({ chance: 0.03 }))).toMatch(/5% to 95%/);
    expect(callRowCheck(callBase({ base_cases: 29 }))).toMatch(/30 cases/);
    expect(callRowCheck(callBase({ horizon_days: 0 }))).toMatch(/horizon/);
    expect(
      callRowCheck(callBase({ verdict: "No view yet", chance: null, base_cases: 0 })),
    ).toBeNull();
  });

  it("a thin or moved bucket needs limited evidence in the text", () => {
    expect(bucketLimited(29, 0.5, 0.5)).toBe(true);
    expect(bucketLimited(400, 0.6, 0.5)).toBe(true);
    expect(bucketLimited(400, 0.55, 0.5)).toBe(false);
    expect(callRowCheck(callBase({ limited: true }))).toMatch(/limited evidence/);
    const withText = sentences([
      { key: "limited", en: "Limited evidence: few cases.", bn: "প্রমাণ সীমিত।" },
    ]);
    expect(callRowCheck(callBase({ limited: true, sentences_json: withText }))).toBeNull();
  });

  it("the door holds back the single bad call and writes the rest", async () => {
    const t = await makeApp();
    const res = (await (
      await t.signed("POST", "/api/calls/publish", {
        rows: [callBase(), callBase({ id: "NSE:BAD:2026-11-28:63", symbol: "BAD", chance: 0.99 })],
      })
    ).json()) as { written: number; held: { id: string }[] };
    expect(res.written).toBe(1);
    expect(res.held.map((h) => h.id)).toEqual(["NSE:BAD:2026-11-28:63"]);
  });
});
