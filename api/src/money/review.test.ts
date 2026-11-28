// Guards for the chapter 10 money review (docs/areas/MONEY-review.md): each test pins one fixed wrong number.
import { describe, expect, it } from "vitest";
import { rsuView } from "../../../money/src/rsu/rsu";
import { harvest, rulesFor } from "../../../money/src/tax/tax";
import { makeApp } from "../testkit";

const trade = (
  key: string,
  side: string,
  date: string,
  qty: number,
  price: number,
  symbol = "AAA",
  currency = "INR",
) =>
  `insert into trades (trade_key,account,source,source_ref,kind,symbol,isin,side,trade_date,quantity,price,currency,status)
   values ('${key}','main','tradebook','r','stock','${symbol}','TEST${symbol}','${side}','${date}',${qty},${price},'${currency}','confirmed');`;

describe("review: corporate actions reach XIRR and risk", () => {
  it("values a split stock at its post-split share count", async () => {
    const { app, db } = await makeApp();
    await app.request("/api/money/xirr");
    await db.exec(
      `${trade("b", "buy", "2024-01-01", 10, 100)}
       insert into corporate_actions (symbol,ex_date,kind,isin,numerator,denominator) values ('AAA','2024-06-01','split','TESTAAA',2,1);
       insert into stock_history (symbol,exchange,date,close) values ('AAA','NSE','2025-01-01',55);`,
    );
    const x = (await (await app.request("/api/money/xirr")).json()) as {
      holdings: { quantity: number; value: number }[];
      portfolio: { xirr: number };
    };
    expect(x.holdings[0]).toMatchObject({ quantity: 20, value: 1100 });
    expect(x.portfolio.xirr).toBeCloseTo(0.1, 1);
    const r = (await (await app.request("/api/money/risk")).json()) as {
      concentration: { total: number };
    };
    expect(r.concentration.total).toBe(1100);
  });
});

describe("review: harvest", () => {
  it("an unsold losing stock frees no tax-free room for the next stock", () => {
    const lots = [
      {
        id: 1,
        symbol: "LOSS",
        isin: "L",
        acquired_on: "2020-01-01",
        quantity: 10,
        cost_per_unit: 200,
      },
      {
        id: 2,
        symbol: "GAIN",
        isin: "G",
        acquired_on: "2020-02-01",
        quantity: 2000,
        cost_per_unit: 100,
      },
    ];
    const h = harvest(lots, { LOSS: 100, GAIN: 200 }, "2026-06-01", rulesFor(2026), 0, true);
    expect(h.gain_candidates).toEqual([
      expect.objectContaining({ symbol: "GAIN", quantity: 1250, gain: 125000 }),
    ]);
    expect(h.gain_room_left).toBe(0);
  });

  it("uses today's tax year for the room, whatever year was asked", async () => {
    const { app, db } = await makeApp({ now: () => new Date("2026-06-01T06:00:00Z") });
    await app.request("/api/money/tax?fy=2026");
    await db.exec(
      trade("b", "buy", "2020-01-01", 3000, 100) +
        trade("s", "sell", "2025-08-01", 1000, 200) +
        "insert into stock_history (symbol,exchange,date,close) values ('AAA','NSE','2026-05-29',200);",
    );
    const t = (await (await app.request("/api/money/tax?fy=2025")).json()) as {
      net: { ltcg_equity: number };
      ltcg_equity_room_left: number;
      harvest: { gain_room: number };
    };
    expect(t.net.ltcg_equity).toBe(100000);
    expect(t.ltcg_equity_room_left).toBe(25000); // the asked year's figure
    expect(t.harvest.gain_room).toBe(125000); // nothing booked yet in 2026-27
  });
});

describe("review: RSUs", () => {
  it("counts 24 calendar months, not 730 days, across a leap year", () => {
    const v = (asOf: string) =>
      rsuView({
        lots: [{ acquiredOn: "2022-03-01", quantity: 1, costUsd: 10 }],
        priceUsd: 20,
        rate: 1,
        rateOn: () => 1,
        rule: { longTermMonths: 24, shortRate: 0.3, longRate: 0.125 },
        asOf,
      }).taxInr;
    expect(v("2024-03-01")).toBeCloseTo(3); // 731 days, but exactly 24 months: short term
    expect(v("2024-03-02")).toBeCloseTo(1.25);
  });

  it("sets a short-term loss off against long-term gain, adds cess, and shows only future vests", async () => {
    const { app, db, signed } = await makeApp({ now: () => new Date("2026-06-01T06:00:00Z") });
    await app.request("/api/money/rsu");
    await db.exec(
      trade("v1", "buy", "2023-01-10", 10, 100, "USX", "USD") +
        trade("v2", "buy", "2025-12-10", 5, 200, "USX", "USD") +
        "insert into fx_rates (day, usd_inr) values ('2023-01-10', 80), ('2025-12-10', 85), ('2026-05-29', 90);",
    );
    await signed("POST", "/api/money/us-prices", {
      symbol: "USX",
      rows: [{ date: "2026-05-29", close: 150 }],
    });
    const j = (await (await app.request("/api/money/rsu")).json()) as {
      symbols: { view: { taxInr: number }; expectedVests: { day: string }[] }[];
    };
    const long = 10 * 150 * 90 - 10 * 100 * 80; // 55000
    const short = 5 * 150 * 90 - 5 * 200 * 85; // -17500
    expect(j.symbols[0]?.view.taxInr).toBeCloseTo((long + short) * 0.125 * 1.04, 6);
    expect(j.symbols[0]?.expectedVests.map((v) => v.day)).toEqual([
      "2026-06-10",
      "2026-09-10",
      "2026-12-10",
      "2027-03-10",
    ]);
  });
});

describe("review: dividend calendar", () => {
  it("moves a 29 February ex-date to 1 March next year", async () => {
    const { app, db, signed } = await makeApp({ now: () => new Date("2025-01-10T06:00:00Z") });
    await app.request("/api/money/calendar");
    await db.exec(trade("b", "buy", "2023-01-01", 10, 100));
    await signed("POST", "/api/money/dividends", {
      symbol: "AAA",
      rows: [{ ex_date: "2024-02-29", per_share: 2 }],
    });
    const j = (await (await app.request("/api/money/calendar")).json()) as {
      dividends: { date: string; cash: number }[];
    };
    expect(j.dividends).toEqual([expect.objectContaining({ date: "2025-03-01", cash: 20 })]);
  });
});

describe("review: grandfathering", () => {
  it("warns when a pre-2018 equity lot is sold at actual cost", async () => {
    const { app, db } = await makeApp({ now: () => new Date("2026-06-01T06:00:00Z") });
    await app.request("/api/money/tax?fy=2025");
    await db.exec(
      trade("b", "buy", "2017-05-01", 10, 100) + trade("s", "sell", "2025-08-01", 10, 300),
    );
    const t = (await (await app.request("/api/money/tax?fy=2025")).json()) as {
      warnings: string[];
    };
    expect(t.warnings.some((w) => w.includes("1 Feb 2018") && w.includes("AAA"))).toBe(true);
  });
});
