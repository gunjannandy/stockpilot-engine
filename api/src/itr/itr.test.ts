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

describe("ITR pack Schedule FA", () => {
  it("fills peak and closing value from the stored dollar closes", async () => {
    const { app, db } = await makeApp({ now: () => new Date("2026-06-01T06:00:00Z") });
    await app.request("/api/itr/pack?fy=abc"); // applies the migrations
    await db.exec(
      `insert into trades (trade_key,account,source,source_ref,kind,symbol,isin,side,trade_date,quantity,price,currency,status)
       values ('u','main','tradebook','r','stock','USX','US0000000001','buy','2025-01-10',10,100,'USD','confirmed');
       insert into fx_rates (day, usd_inr) values ('2024-11-25', 80), ('2026-05-29', 80);
       insert into us_prices (symbol, date, close) values ('USX','2025-06-30',120), ('USX','2025-12-31',110);`,
    );
    const res = await app.request("/api/itr/pack?fy=2025");
    expect(res.status).toBe(200);
    const text = new TextDecoder().decode(new Uint8Array(await res.arrayBuffer()));
    // symbol,isin,units,initial (10 x 100 x 80),peak (10 x 120 x 80),closing (10 x 110 x 80)
    expect(text).toContain("USX,US0000000001,10,80000,96000,88000");
  });
});
