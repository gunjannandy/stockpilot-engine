// C-068-1: holdings and trades without account or source are rejected.

import { expect, it } from "vitest";
import { mapHoldings, storeSync } from "../api/src/kite/sync";
import { makeApp } from "../api/src/testkit";
import { RawHolding, RawTrade } from "../contract/src";

const holding = {
  account: "primary",
  source: "kite",
  snapshot_at: "2026-11-28T09:00:00+05:30",
  kind: "stock",
  symbol: "AAA",
  isin: null,
  quantity: 1,
  avg_price: 10,
};
const trade = {
  account: "primary",
  source: "kite",
  trade_key: "kite:1",
  source_ref: "o1",
  kind: "stock",
  symbol: "AAA",
  isin: null,
  side: "buy",
  trade_date: "2026-11-26",
  quantity: 1,
  price: 10,
};

it("C-068-1 a holding or trade without account or source is rejected", () => {
  expect(RawHolding.safeParse(holding).success).toBe(true);
  expect(RawTrade.safeParse(trade).success).toBe(true);
  for (const k of ["account", "source"] as const) {
    expect(RawHolding.safeParse({ ...holding, [k]: undefined }).success).toBe(false);
    expect(RawHolding.safeParse({ ...holding, [k]: "" }).success).toBe(false);
    expect(RawTrade.safeParse({ ...trade, [k]: undefined }).success).toBe(false);
    expect(RawTrade.safeParse({ ...trade, [k]: "" }).success).toBe(false);
  }
});

it("C-068-1 every stored row carries account and source", async () => {
  const t = await makeApp();
  await t.app.request("/api/ping"); // first request applies the migrations
  const data = {
    holdings: [{ tradingsymbol: "AAA", quantity: 3, average_price: 5 }],
    mf_holdings: [],
    trades: [],
    positions: {},
    margins: {},
    gtts: [],
  };
  await storeSync({ d1: t.db, now: () => new Date("2026-11-28T03:30:00Z") }, data);
  const rows = (await t.db.prepare("select account, source from holdings").all()) as {
    results: { account: string; source: string }[];
  };
  expect(rows.results.length).toBe(1);
  expect(rows.results.every((r) => r.account && r.source)).toBe(true);
  expect(mapHoldings(data, "x").every((h) => h.account && h.source)).toBe(true);
});
