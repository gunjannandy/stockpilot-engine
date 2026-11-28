import { describe, expect, it } from "vitest";
import { makeApp } from "../testkit";

describe("portfolio routes", () => {
  it("serves the newest snapshot of each source, trades and actions with their terms", async () => {
    const { app, db } = await makeApp();
    await app.request("/api/portfolio/trades"); // first request applies the migrations
    await db.exec(`
      insert into holdings values ('main','kite','2026-11-01T10:00:00+05:30','stock','AAA','TESTID0001',5,10);
      insert into holdings values ('main','kite','2026-11-02T10:00:00+05:30','stock','AAA','TESTID0001',7,10);
      insert into holdings values ('main','coin','2026-10-30T10:00:00+05:30','mf','FND',null,3,20);
      insert into trades (trade_key,account,source,source_ref,kind,symbol,isin,side,trade_date,quantity,price,currency,status)
        values ('t1','main','tradebook','r','stock','AAA','TESTID0001','buy','2026-01-05',5,10,'INR','confirmed');
      insert into corporate_actions (symbol,ex_date,kind,isin,numerator,denominator) values ('AAA','2026-06-01','demerger','TESTID0001',1,1);
      insert into action_terms (symbol,ex_date,kind,new_symbol,cost_fraction) values ('AAA','2026-06-01','demerger','BBB',0.3);
    `);
    const h = (await (await app.request("/api/portfolio/holdings")).json()) as {
      holdings: { source: string; quantity: number }[];
    };
    expect(h.holdings.map((x) => [x.source, x.quantity])).toEqual([
      ["coin", 3],
      ["kite", 7],
    ]);
    const t = (await (await app.request("/api/portfolio/trades")).json()) as { trades: unknown[] };
    expect(t.trades).toHaveLength(1);
    const a = (await (await app.request("/api/portfolio/corporate-actions")).json()) as {
      actions: { terms: { cost_fraction: number } | null }[];
    };
    expect(a.actions[0]?.terms?.cost_fraction).toBe(0.3);
  });

  it("stores the budget and mix as replaced whole settings, and refuses a bad mix", async () => {
    const { app } = await makeApp();
    const put = (path: string, body: unknown) =>
      app.request(path, {
        method: "PUT",
        body: JSON.stringify(body),
        headers: { "content-type": "application/json" },
      });
    expect(
      (await put("/api/portfolio/budget", { default: 1000, months: { "2026-11": 2500 } })).status,
    ).toBe(200);
    expect((await put("/api/portfolio/budget", { default: 900 })).status).toBe(200);
    expect((await put("/api/portfolio/mix", { mix: { stocks: 0.5, gold: 0.2 } })).status).toBe(400);
    expect((await put("/api/portfolio/mix", { mix: { stocks: 0.7, gold: 0.3 } })).status).toBe(200);
    const s = (await (await app.request("/api/portfolio/settings")).json()) as {
      budget: unknown;
      mix: unknown;
    };
    expect(s.budget).toEqual({ default: 900, months: {} });
    expect(s.mix).toEqual({ gold: 0.3, stocks: 0.7 });
  });
});
