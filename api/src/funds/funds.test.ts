import type { FundRow } from "@stockpilot/contract";
import { describe, expect, it } from "vitest";
import { makeApp } from "../testkit";

const fund = (n: number, over: Partial<FundRow> = {}): FundRow => ({
  id: `fund-${n}`,
  code: 100000 + n,
  name: n === 1 ? "Alpha Flexi Cap Fund" : `Fund ${n}`,
  amc: n === 1 ? "Alpha Mutual Fund" : "Other Mutual Fund",
  category: n % 2 ? "Equity Scheme - Flexi Cap Fund" : "Equity Scheme - Large Cap Fund",
  nav: 12.5,
  nav_date: "2026-11-27",
  ter: 0.6,
  ter_regular: 1.5,
  aum_cr: 1200,
  r1: 10,
  r3: 12,
  r5: 14,
  cat_r1: 9,
  cat_r3: 11,
  cat_r5: 13,
  category_n: 20,
  max_fall: -18.5,
  roll_min: -12,
  roll_median: 11,
  roll_max: 45,
  roll_loss_share: 0.1,
  navs_json: '[["2026-11-13",12.1],["2026-11-20",12.5]]',
  ...over,
});

const stamp = {
  dataset: "funds",
  source: "mfapi",
  fetched_at: "2026-11-28T21:00:00+05:30",
  as_of: "2026-11-28",
};

async function publish(rows: unknown[]) {
  const t = await makeApp();
  const posted = await t.signed("POST", "/api/publish/rows", { ...stamp, run_id: "f1", rows });
  expect(posted.status).toBe(200);
  const fin = await t.signed("POST", "/api/publish/finish", { dataset: "funds", run_id: "f1" });
  return { t, fin };
}

describe("funds routes", () => {
  it("answers empty before any run is published", async () => {
    const { app } = await makeApp();
    const r = (await (await app.request("/api/funds")).json()) as { total: number };
    expect(r.total).toBe(0);
    expect((await app.request("/api/funds/nope")).status).toBe(404);
  });

  it("lists without NAVs, searches by words and category, and gives one fund whole", async () => {
    const { t, fin } = await publish(Array.from({ length: 120 }, (_, i) => fund(i + 1)));
    expect(fin.status).toBe(200);
    const list = (await (await t.app.request("/api/funds?q=alpha%20flexi")).json()) as {
      total: number;
      funds: Record<string, unknown>[];
    };
    expect(list.total).toBe(1);
    expect(list.funds[0]?.name).toBe("Alpha Flexi Cap Fund");
    expect(list.funds[0]).not.toHaveProperty("navs_json");
    const cat = (await (
      await t.app.request("/api/funds?category=Equity%20Scheme%20-%20Large%20Cap%20Fund&limit=5")
    ).json()) as { total: number; funds: unknown[]; categories: string[] };
    expect(cat.total).toBe(60);
    expect(cat.funds).toHaveLength(5);
    expect(cat.categories).toHaveLength(2);
    const one = (await (await t.app.request("/api/funds/fund-1")).json()) as {
      fund: { navs: unknown[] };
    };
    expect(one.fund.navs).toHaveLength(2);
  });

  it("fails a run of fewer than 100 funds, and holds back a fund with one NAV", async () => {
    const { fin } = await publish(Array.from({ length: 5 }, (_, i) => fund(i + 1)));
    expect(fin.status).toBe(422);
    const t = await makeApp();
    const r = await t.signed("POST", "/api/publish/rows", {
      ...stamp,
      run_id: "f2",
      rows: [fund(1, { navs_json: '[["2026-11-20",12.5]]' })],
    });
    expect(((await r.json()) as { held_back: number }).held_back).toBe(1);
  });
});
