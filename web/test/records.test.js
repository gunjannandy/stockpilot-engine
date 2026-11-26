// T29: Holdings, Tax, Trading record, Our record and RSUs read from the live API (views_get), with the v10 behaviour kept.
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import "../public/screens/records.js";   // a plain browser script: it puts SPRecords on the global
const R = globalThis.SPRecords;
const rows = JSON.parse(readFileSync(new URL("../../tests/fixtures/live/tables/views.json", import.meta.url), "utf8"));
const view = n => rows.find(r => r.name === n);
const H = () => JSON.parse(JSON.stringify(view("portfolio").doc.holdings));
const ok = body => ({ ok: true, status: 200, json: async () => body });
const no = status => ({ ok: false, status, json: async () => ({}) });

describe("load: the live API first, the last static file when the API has nothing", () => {
  it("reads each view from /api/v2/views/<name>", async () => {
    const urls = [];
    const f = async u => { urls.push(u); const n = u.split("/").pop(); return ok({ name: n, as_of: "2026-11-25", written_at: "x", doc: view(n).doc }); };
    const r = await R.load(f, async () => { throw new Error("static not needed"); });
    expect(urls.sort()).toEqual(["/api/v2/views/own_record", "/api/v2/views/portfolio", "/api/v2/views/record", "/api/v2/views/smallcase"]);
    expect(r.docs.portfolio.total_value).toBe(view("portfolio").doc.total_value);
    expect(r.live).toEqual({ portfolio: true, smallcase: true, record: true, own_record: true });
  });
  it("falls back to the static file for a view the API does not hold yet (404) or cannot reach", async () => {
    const f = async u => u.endsWith("/portfolio") ? ok({ doc: view("portfolio").doc }) : u.endsWith("/record") ? no(404) : Promise.reject(new Error("offline"));
    const r = await R.load(f, async n => ({ from: "static", n }));
    expect(r.docs.portfolio.holdings.length).toBe(3);
    expect(r.docs.record).toEqual({ from: "static", n: "record" });
    expect(r.docs.smallcase).toEqual({ from: "static", n: "smallcase" });
    expect(r.live).toEqual({ portfolio: true, smallcase: false, record: false, own_record: false });
  });
  it("a view missing everywhere is null, so the screen says there is no data instead of breaking", async () => {
    const r = await R.load(async () => no(404), async () => { throw new Error("404"); });
    expect(r.docs.own_record).toBeNull();
  });
});

describe("Kite / Smallcase / All filter", () => {
  it("counts how many holdings came in through each route", () => {
    expect(R.sourceCounts(H())).toEqual({ all: 3, kite: 3, smallcase: 1 });
  });
  it("All keeps every row as it is", () => {
    expect(R.holdingsFor(H(), "all").map(h => h.quantity)).toEqual([100, 60, 50]);
  });
  it("Smallcase shows only what came in through Smallcase: its units, and its share of the value", () => {
    const r = R.holdingsFor(H(), "smallcase");
    expect(r.map(h => h.symbol)).toEqual(["FIXB"]);
    expect(r[0].quantity).toBe(40);
    expect(r[0].value).toBe(40 * 450);
    expect(r[0].gain_pct).toBe(-0.1);   // the gain per unit does not change with the route
    expect(r[0].share).toBe(1);
  });
  it("Kite shows its own units, and the shares add up to 100%", () => {
    const r = R.holdingsFor(H(), "kite");
    expect(r.find(h => h.symbol === "FIXB").quantity).toBe(20);
    expect(r.reduce((a, h) => a + h.share, 0)).toBeCloseTo(1, 3);
  });
  it("a holding with no route split counts as Kite", () => {
    const h = H().map(x => { delete x.by_source; return x; });
    expect(R.sourceCounts(h)).toEqual({ all: 3, kite: 3, smallcase: 0 });
    expect(R.holdingsFor(h, "smallcase")).toEqual([]);
  });
});

describe("the totals line is the sum of the rows shown (the old check-10 rule)", () => {
  for (const src of ["all", "kite", "smallcase"]) it(`${src}: value, cost and gain agree with the rows`, () => {
    const r = R.holdingsFor(H(), src), s = R.summary(r);
    expect(s.count).toBe(r.length);
    expect(s.value).toBe(r.reduce((a, h) => a + h.value, 0));
    expect(s.cost).toBeCloseTo(r.reduce((a, h) => a + h.avg_cost * h.quantity, 0), 6);
    expect(s.gain).toBeCloseTo(s.value - s.cost, 6);
    expect(s.gain_pct).toBeCloseTo(s.cost ? (s.value - s.cost) / s.cost : 0, 6);
  });
  it("the stored total equals the sum of the stored rows", () => {
    expect(R.summary(R.holdingsFor(H(), "all")).value).toBe(view("portfolio").doc.total_value);
  });
});

describe("units check", () => {
  it("says which holdings have units our lots do not explain, and by how many", () => {
    const u = R.unitsCheck(H());
    expect(u.checked).toBe(3);
    expect(u.off).toEqual([{ symbol: "FIXB", name: "Fixture Beta Ltd", held: 60, lots: 58, diff: 2 }]);
    expect(u.noted.map(n => n.symbol)).toEqual(["FIXB"]);
  });
  it("is clean when every holding's lots add up", () => {
    const h = H(); h[1].lots_units = 60; h[1].check = null;
    expect(R.unitsCheck(h)).toEqual({ checked: 3, off: [], noted: [] });
  });
  it("skips a holding that has no lot count (funds held only at Kite)", () => {
    const h = H(); h[1].lots_units = null;
    expect(R.unitsCheck(h).checked).toBe(2);
  });
});
