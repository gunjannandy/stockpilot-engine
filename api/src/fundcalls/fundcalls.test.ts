import type { FundCallRow } from "@stockpilot/contract";
import { describe, expect, it } from "vitest";
import { makeApp } from "../testkit";

const row = (id: string, over: Partial<FundCallRow> = {}): FundCallRow => ({
  id,
  kind: "call",
  name: `Fund ${id}`,
  category: "Equity Scheme - Flexi Cap Fund",
  call: "buy",
  rank: 1,
  of: 20,
  quartile: 1,
  chance: 0.6,
  cases: 80,
  periods: 5,
  avg_excess: 1.2,
  reasons: "",
  caveat: "c",
  as_of: "2026-11-28",
  ...over,
});

describe("fund calls route", () => {
  it("answers empty before any run is published", async () => {
    const { app } = await makeApp();
    const r = (await (await app.request("/api/fund-calls")).json()) as { calls: unknown[] };
    expect(r.calls).toEqual([]);
  });

  it("gives buys before watches, best rank first, and the track record apart", async () => {
    const t = await makeApp();
    const rows = [
      row("w1", { call: "watch", rank: 1 }),
      row("b2", { rank: 3 }),
      row("b1", { rank: 2 }),
      ...Array.from({ length: 3 }, (_, i) =>
        row(`track:Equity Scheme:${i + 1}`, {
          kind: "track",
          call: null,
          rank: null,
          of: null,
          quartile: i + 1,
        }),
      ),
    ];
    const stamp = {
      dataset: "fund_calls",
      source: "funds",
      fetched_at: "2026-11-28T21:00:00+05:30",
      as_of: "2026-11-28",
    };
    expect(
      (await t.signed("POST", "/api/publish/rows", { ...stamp, run_id: "c1", rows })).status,
    ).toBe(200);
    expect(
      (await t.signed("POST", "/api/publish/finish", { dataset: "fund_calls", run_id: "c1" }))
        .status,
    ).toBe(200);
    const r = (await (await t.app.request("/api/fund-calls")).json()) as {
      calls: { id: string }[];
      track: unknown[];
    };
    expect(r.calls.map((c) => c.id)).toEqual(["b1", "b2", "w1"]);
    expect(r.track).toHaveLength(3);
  });
});
