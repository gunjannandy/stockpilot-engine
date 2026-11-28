import { type FundHoldingsRow, fundHoldings, fundOverlap } from "@stockpilot/contract";
import { describe, expect, it } from "vitest";
import { makeApp } from "../testkit";

const row = (n: number): FundHoldingsRow => ({
  id: `fund-${n}`,
  name: `Fund ${n}`,
  amc: "Alpha Mutual Fund",
  as_of: "2026-10-31",
  holdings_json: JSON.stringify([
    ["INE-A", "Stock A", 6.5],
    ["INE-B", "Stock B", 3.5],
    ["GILT-1", "Gilt", 10],
    ["INE-C", "Stock C", null],
  ]),
});

const stamp = {
  dataset: "fund_holdings",
  source: "fund houses",
  fetched_at: "2026-11-28T22:00:00+05:30",
  as_of: "2026-11-28",
};

describe("fund overlap (C-076-1)", () => {
  const h = fundHoldings(row(1).holdings_json);
  it("counts shared stocks, their weight and their share of the fund's equities", () => {
    const o = fundOverlap(h, ["ine-a", "INE-B", "INE-Z"]);
    expect(o.n_shared).toBe(2);
    expect(o.n_held).toBe(3);
    expect(o.pct_nav).toBe(10);
    expect(o.pct_of_fund_stocks).toBe(66.7);
  });
  it("is zero for no holdings, an empty fund and a bad text", () => {
    expect(fundOverlap(h, []).pct_nav).toBe(0);
    expect(fundOverlap([], ["INE-A"]).pct_of_fund_stocks).toBe(0);
    expect(fundHoldings("not json")).toEqual([]);
  });
});

describe("fund holdings routes", () => {
  it("answers empty first, then lists without holdings and gives one fund whole", async () => {
    const t = await makeApp();
    expect(
      ((await (await t.app.request("/api/fund-holdings")).json()) as { funds: [] }).funds,
    ).toEqual([]);
    expect((await t.app.request("/api/fund-holdings/nope")).status).toBe(404);
    const rows = Array.from({ length: 25 }, (_, i) => row(i + 1));
    expect(
      (await t.signed("POST", "/api/publish/rows", { ...stamp, run_id: "h1", rows })).status,
    ).toBe(200);
    expect(
      (await t.signed("POST", "/api/publish/finish", { dataset: "fund_holdings", run_id: "h1" }))
        .status,
    ).toBe(200);
    const list = (await (await t.app.request("/api/fund-holdings")).json()) as {
      funds: Record<string, unknown>[];
    };
    expect(list.funds).toHaveLength(25);
    expect(list.funds[0]).not.toHaveProperty("holdings_json");
    const one = (await (await t.app.request("/api/fund-holdings/fund-3")).json()) as {
      fund: { holdings: unknown[] };
    };
    expect(one.fund.holdings).toHaveLength(4);
  });
  it("fails a run of fewer than 20 funds", async () => {
    const t = await makeApp();
    await t.signed("POST", "/api/publish/rows", { ...stamp, run_id: "h2", rows: [row(1)] });
    expect(
      (await t.signed("POST", "/api/publish/finish", { dataset: "fund_holdings", run_id: "h2" }))
        .status,
    ).toBe(422);
  });
});
