// R2: the ingest door takes the v2 copy's tables, replaces by key (a null isin included), holds a bad row back,
// and a rerun leaves the table as it was.
import { expect, it } from "vitest";
import { makeApp } from "../api/src/testkit";

it("copies through the door once, however often it is run", async () => {
  const { signed, db } = await makeApp();
  const hold = {
    account: "main",
    source: "kite",
    snapshot_at: "2026-11-26T15:40:00+05:30",
    kind: "stock",
    symbol: "AAA",
    isin: null,
    quantity: 1,
    avg_price: 2,
  };
  const body = { dataset: "holdings", run_id: "m-1", rows: [hold, { symbol: "bad" }] };
  for (let i = 0; i < 2; i++) {
    const res = await signed("POST", "/api/ingest", body);
    expect(await res.json()).toEqual({ accepted: 1, held_back: 1 });
  }
  const n = await db.prepare("select count(*) as n from holdings").first<{ n: number }>();
  expect(n?.n).toBe(1);
  const r = await signed("POST", "/api/ingest", {
    dataset: "archived_days",
    run_id: "m-2",
    rows: [{ day: "2026-11-25", payload: "{}" }],
  });
  expect(await r.json()).toEqual({ accepted: 1, held_back: 0 });
  const w = await signed("POST", "/api/ingest", { dataset: "nope", run_id: "m-3", rows: [] });
  expect(w.status).toBe(403);
});
