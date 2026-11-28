import { describe, expect, it } from "vitest";
import { makeApp } from "../testkit";

const trade = (key: string, side: string, date: string, qty: number, price: number) =>
  [key, "primary", "kite", "o1", "stock", "S001", null, side, date, qty, price] as const;

describe("ITR pack route", () => {
  it("refuses a bad year, says so when no trades are stored, then sends a zip", async () => {
    const { app, db } = await makeApp();
    expect((await app.request("/api/itr/pack?fy=abc")).status).toBe(400);
    expect((await app.request("/api/itr/pack?fy=2025")).status).toBe(404);
    for (const t of [
      trade("k1", "buy", "2024-01-10", 10, 100),
      trade("k2", "sell", "2025-06-10", 10, 150),
    ]) {
      await db
        .prepare(
          "insert into trades (trade_key, account, source, source_ref, kind, symbol, isin, side, trade_date, quantity, price) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        )
        .bind(...t)
        .run();
    }
    const res = await app.request("/api/itr/pack?fy=2025");
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe("application/zip");
    const bytes = new Uint8Array(await res.arrayBuffer());
    expect([bytes[0], bytes[1]]).toEqual([0x50, 0x4b]);
    expect(new TextDecoder().decode(bytes)).toContain("summary.json");
  });
});
