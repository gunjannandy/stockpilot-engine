import { describe, expect, it } from "vitest";
import { SqliteD1 } from "../../../adapters/src/core";
import { migrationFiles } from "../../migrate/discover";
import { loadPairs, loadRebuild } from "./load";

async function fresh() {
  const db = new SqliteD1();
  for (const m of migrationFiles()) await db.exec(m.sql);
  return db;
}
const trade = (
  db: SqliteD1,
  key: string,
  side: string,
  date: string,
  qty: number,
  price: number,
  extra: Partial<Record<string, unknown>> = {},
) =>
  db
    .prepare(
      "insert into trades (trade_key, account, source, source_ref, kind, symbol, isin, side, trade_date, quantity, price, currency, status) values (?, 'primary', 'tradebook', 'r', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
    )
    .bind(
      key,
      extra.kind ?? "stock",
      extra.symbol ?? "ABC",
      extra.isin ?? "TESTID0001",
      side,
      date,
      qty,
      price,
      extra.currency ?? "INR",
      extra.status ?? "confirmed",
    )
    .run();

describe("lots loader", () => {
  it("applies a stored split to the lots rebuilt from stored trades", async () => {
    const db = await fresh();
    await trade(db, "b1", "buy", "2024-01-10", 10, 100);
    await db.exec(
      "insert into corporate_actions (symbol, ex_date, kind, isin, numerator, denominator) values ('ABC', '2024-06-01', 'split', 'TESTID0001', 2, 1)",
    );
    const { lots } = await loadRebuild(db);
    const l = lots.find((x) => x.symbol === "ABC");
    expect(l?.quantity).toBe(20);
    expect(l?.costPerUnit).toBe(50);
  });

  it("reads a demerger's terms from action_terms", async () => {
    const db = await fresh();
    await trade(db, "b1", "buy", "2024-01-10", 10, 100);
    await db.exec(`insert into corporate_actions (symbol, ex_date, kind, isin, numerator, denominator) values ('ABC', '2024-06-01', 'demerger', 'TESTID0001', 1, 1);
      insert into action_terms (symbol, ex_date, kind, new_isin, new_symbol, cost_fraction) values ('ABC', '2024-06-01', 'demerger', 'TESTID0002', 'NEWCO', 0.25)`);
    const { lots } = await loadRebuild(db);
    expect(lots.find((x) => x.symbol === "NEWCO")?.quantity).toBe(10);
  });

  it("uses Fidelity statement rows only when a dollar rate is given", async () => {
    const db = await fresh();
    await trade(db, "v1", "vest", "2024-02-01", 5, 50, {
      kind: "rsu",
      symbol: "CORP",
      isin: "US0000000001",
      currency: "USD",
    });
    await db.exec(
      "insert into fidelity_lots (as_of, symbol, isin, acquired_on, quantity, cost_basis_inr) values ('2024-03-01', 'CORP', 'US0000000001', '2024-01-31', 4, 16600)",
    );
    const without = await loadRebuild(db);
    expect(without.lots.filter((l) => l.kind === "rsu").map((l) => l.sourceRef)).not.toContain(
      "statement:2024-03-01:2024-01-31",
    );
    expect(without.lots.some((l) => l.kind === "rsu" && l.quantity === 5)).toBe(true);
    const withRate = await loadRebuild(db, { rateOn: () => 83 });
    expect(withRate.lots.some((l) => l.sourceRef === "statement:2024-03-01:2024-01-31")).toBe(true);
  });

  it("pairs each sale with its lot and carries the route from the trade tag", async () => {
    const db = await fresh();
    await trade(db, "b1", "buy", "2024-01-10", 10, 100);
    await trade(db, "s1", "sell", "2024-08-10", 4, 150);
    await db.exec("insert into trade_tags (trade_key, placed_by) values ('b1', 'smallcase')");
    const pairs = await loadPairs(db);
    expect(pairs).toHaveLength(1);
    expect(pairs[0]).toMatchObject({
      route: "smallcase",
      quantity: 4,
      cost: 400,
      proceeds: 600,
      gain: 200,
    });
  });

  it("gives nothing when no trades are stored", async () => {
    const db = await fresh();
    expect((await loadRebuild(db)).lots).toEqual([]);
    expect(await loadPairs(db)).toEqual([]);
  });
});
