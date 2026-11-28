import { describe, expect, it } from "vitest";
import { SqliteD1 } from "../../../adapters/src/core";
import { migrationFiles } from "../../migrate/discover";
import { loadRateOn, refreshRates } from "./rates";

async function fresh() {
  const db = new SqliteD1();
  for (const m of migrationFiles()) await db.exec(m.sql);
  return db;
}
const feed = (rates: Record<string, number>) => async () => ({
  ok: true,
  json: async () => ({
    rates: Object.fromEntries(Object.entries(rates).map(([d, r]) => [d, { INR: r }])),
  }),
});

describe("USD/INR rates", () => {
  it("is null with nothing stored, and takes the last rate on or before a day", async () => {
    const db = await fresh();
    expect(await loadRateOn(db)).toBeNull();
    await refreshRates(
      db,
      "2025-01-10",
      "2025-01-01",
      feed({ "2025-01-03": 85.5, "2025-01-06": 85.9 }),
    );
    const r = await loadRateOn(db);
    expect(r?.("2025-01-05")).toBe(85.5);
    expect(r?.("2025-01-06")).toBe(85.9);
    expect(r?.("2025-01-02")).toBeNull();
  });
  it("keeps stored rates when the feed fails", async () => {
    const db = await fresh();
    await refreshRates(db, "2025-01-10", "2025-01-01", feed({ "2025-01-03": 85.5 }));
    const n = await refreshRates(db, "2025-02-01", "2025-01-01", async () => {
      throw new Error("down");
    });
    expect(n).toBe(0);
    expect((await loadRateOn(db))?.("2025-01-31")).toBe(85.5);
  });
});
