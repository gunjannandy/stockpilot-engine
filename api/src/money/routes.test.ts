import { describe, expect, it } from "vitest";
import { makeApp } from "../testkit";

const trade = (key: string, side: string, date: string, qty: number, price: number) =>
  `insert into trades (trade_key,account,source,source_ref,kind,symbol,isin,side,trade_date,quantity,price,currency,status)
   values ('${key}','main','tradebook','r','stock','AAA','TESTID0001','${side}','${date}',${qty},${price},'INR','confirmed');`;

describe("money tax route", () => {
  it("books a long-term gain in the year it was sold, with its exempt room", async () => {
    const { app, db } = await makeApp();
    await app.request("/api/money/tax?fy=2026"); // first request applies the migrations
    await db.exec(
      trade("b", "buy", "2024-01-10", 10, 100) + trade("s", "sell", "2025-08-01", 10, 150),
    );
    const r = await app.request("/api/money/tax?fy=2025");
    const j = (await r.json()) as {
      rows: { gain: number; term: string }[];
      net: { ltcg_equity: number };
      ltcg_equity_room_left: number;
      label: string;
    };
    expect(j.label).toBe("2025-26");
    expect(j.rows.map((x) => [x.gain, x.term])).toEqual([[500, "long"]]);
    expect(j.net.ltcg_equity).toBe(500);
    const other = (await (await app.request("/api/money/tax?fy=2026")).json()) as {
      rows: unknown[];
    };
    expect(other.rows).toEqual([]);
  });
  it("refuses a nonsense year", async () => {
    const { app } = await makeApp();
    expect((await app.request("/api/money/tax?fy=abc")).status).toBe(400);
  });
});

describe("money xirr route", () => {
  it("works out a return from trades and the newest close, null without a price", async () => {
    const { app, db } = await makeApp();
    await app.request("/api/money/xirr");
    await db.exec(
      trade("b", "buy", "2024-01-01", 10, 100) +
        "insert into stock_history (symbol,exchange,date,close) values ('AAA','NSE','2025-01-01',110);",
    );
    const j = (await (await app.request("/api/money/xirr")).json()) as {
      as_of: string;
      portfolio: { xirr: number; nifty: null };
      holdings: { value: number }[];
    };
    expect(j.as_of).toBe("2025-01-01");
    expect(j.holdings[0]?.value).toBe(1100);
    expect(j.portfolio.xirr).toBeCloseTo(0.1, 1);
    expect(j.portfolio.nifty).toBeNull();
  });
  it("says so when a held stock has no price", async () => {
    const { app, db } = await makeApp();
    await app.request("/api/money/xirr");
    await db.exec(trade("b", "buy", "2024-01-01", 10, 100));
    const j = (await (await app.request("/api/money/xirr")).json()) as {
      portfolio: { xirr: null };
      warnings: string[];
    };
    expect(j.portfolio.xirr).toBeNull();
    expect(j.warnings.length).toBe(1);
  });
});
