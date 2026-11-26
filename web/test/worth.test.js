// T24: Worth following. One list; no held stock; snooze and cross; Analyse starts a job and shows its progress.
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import "../public/live.js";
import "../public/screens/worth.js";
const W = globalThis.SPWorth;
const fx = n => JSON.parse(readFileSync(new URL(`../../tests/fixtures/live/routes/${n}.json`, import.meta.url), "utf8")).response;
const item = (symbol, o = {}) => ({ symbol, exchange: "NSE", rank: 1, reason: "r", reason_bn: null, since: "2026-11-25T09:15:00+05:30", call: "buy", chance_3m: 0.62, out_of_date: false, ...o });

describe("which stocks show", () => {
  it("never shows a held stock", () => {
    const rows = W.rowsOf([item("A"), item("B", { rank: 2 })], { held: new Set(["A"]), hidden: new Set() });
    expect(rows.map(r => r.symbol)).toEqual(["B"]);
  });
  it("drops hidden stocks and keeps rank order", () => {
    const rows = W.rowsOf([item("C", { rank: 3 }), item("A", { rank: 1 }), item("B", { rank: 2 })], { held: new Set(), hidden: new Set(["B"]) });
    expect(rows.map(r => r.symbol)).toEqual(["A", "C"]);
  });
  it("keeps SME and BSE-only stocks, and the same symbol on two exchanges apart", () => {
    const rows = W.rowsOf([item("X", { exchange: "BSE" }), item("X", { exchange: "NSE", rank: 2 })], { held: new Set(), hidden: new Set() });
    expect(rows).toHaveLength(2);
  });
  it("a held symbol is hidden whatever the exchange", () => {
    expect(W.rowsOf([item("X", { exchange: "BSE" })], { held: new Set(["X"]), hidden: new Set() })).toEqual([]);
  });
});

describe("a row", () => {
  const opt = { name: s => "Name " + s, lang: "en" };
  it("a stock without a call says No forecast yet and offers Analyse", () => {
    const h = W.rowHtml(item("FIXD", { call: null, chance_3m: null, reason: "No forecast yet" }), opt);
    expect(h).toContain("No forecast yet"); expect(h).toContain('data-analyse="FIXD"'); expect(h).not.toContain("meter");
  });
  it("a stock with a call shows the chance and a Strong, Fair or Weak word, not Analyse", () => {
    const h = W.rowHtml(item("A", { chance_3m: 0.62 }), opt);
    expect(h).toContain("62%"); expect(h).toContain("Strong"); expect(h).not.toContain("data-analyse");
    expect(W.meterOf(0.5)).toBe("fair"); expect(W.meterOf(0.3)).toBe("weak"); expect(W.meterOf(0.57)).toBe("strong");
  });
  it("has the snooze and cross buttons", () => {
    const h = W.rowHtml(item("A"), opt);
    expect(h).toContain('data-snooze="A"'); expect(h).toContain('data-dismiss="A"');
  });
  it("marks an out of date forecast", () => { expect(W.rowHtml(item("A", { out_of_date: true }), opt)).toContain("Out of date"); });
  it("escapes the reason and uses the Bengali reason when asked", () => {
    expect(W.rowHtml(item("A", { reason: "<b>x</b>" }), opt)).not.toContain("<b>x</b>");
    expect(W.rowHtml(item("A", { reason: "e", reason_bn: "বাংলা" }), { ...opt, lang: "bn" })).toContain("বাংলা");
  });
  it("shows a job's progress lines in the row while Analyse runs", () => {
    const h = W.rowHtml(item("FIXD", { call: null, chance_3m: null }), { ...opt, job: fx("jobs_get") });
    expect(h).toContain("Reading the numbers"); expect(h).not.toContain("data-analyse");
  });
});

describe("the controller", () => {
  function make(over = {}) {
    const calls = [];
    const fetch = async (url, init = {}) => {
      calls.push({ url, method: init.method || "GET", body: init.body && JSON.parse(init.body) });
      if (url.startsWith("/api/v2/lists/")) return { ok: true, status: 200, json: async () => ({ list_name: "worth_following", items: over.items || [item("A"), item("B", { rank: 2 }), item("D", { rank: 3, call: null, chance_3m: null })] }) };
      if (url === "/api/v2/jobs") return { ok: true, status: 200, json: async () => ({ id: "job_9", status: "queued" }) };
      return { ok: false, status: 500, json: async () => ({}) };
    };
    const queued = [];
    const c = W.createController({ fetch, held: () => new Set(over.held || []), name: s => s, lang: () => "en", queue: async (k, p, d, undo) => { queued.push({ k, p, undo }); return true; }, watchJob: id => calls.push({ watch: id }), rerender: () => {} });
    return { c, calls, queued };
  }
  it("loads the worth_following list and hides held stocks", async () => {
    const { c, calls } = make({ held: ["A"] });
    await c.load();
    expect(calls[0].url).toBe("/api/v2/lists/worth_following");
    expect(c.rows().map(r => r.symbol)).toEqual(["B", "D"]);
  });
  it("snooze hides at once, queues snooze, and Undo brings it back", async () => {
    const { c, queued } = make(); await c.load();
    await c.snooze("B");
    expect(c.rows().map(r => r.symbol)).toEqual(["A", "D"]);
    expect(queued[0]).toMatchObject({ k: "snooze", p: { symbol: "B", scope: "stock" } });
    queued[0].undo(); expect(c.rows().map(r => r.symbol)).toEqual(["A", "B", "D"]);
  });
  it("cross hides and queues dismiss", async () => {
    const { c, queued } = make(); await c.load();
    await c.dismiss("A");
    expect(queued[0]).toMatchObject({ k: "dismiss", p: { symbol: "A", scope: "stock" } });
    expect(c.rows().map(r => r.symbol)).toEqual(["B", "D"]);
  });
  it("Analyse creates an analyse job, watches it, and a second press does nothing", async () => {
    const { c, calls } = make(); await c.load();
    await c.analyse("D"); await c.analyse("D");
    const posts = calls.filter(x => x.url === "/api/v2/jobs");
    expect(posts).toHaveLength(1);
    expect(posts[0].body).toEqual({ kind: "analyse", payload: { symbol: "D", exchange: "NSE" } });
    expect(calls.filter(x => x.watch === "job_9")).toHaveLength(1);
  });
  it("job events fill the row and a finished job reloads the list", async () => {
    const { c, calls } = make(); await c.load(); await c.analyse("D");
    c.onJob({ type: "job", id: "job_9", ...fx("jobs_get") });
    expect(c.jobOf("D").lines).toHaveLength(1);
    const before = calls.filter(x => x.url?.startsWith("/api/v2/lists")).length;
    await c.onJob({ type: "job", id: "job_9", job: { ...fx("jobs_get").job, status: "done", result: "Done" }, lines: [] });
    expect(calls.filter(x => x.url?.startsWith("/api/v2/lists")).length).toBe(before + 1);
  });
  it("a failed list load is reported, not blank", async () => {
    const c = W.createController({ fetch: async () => ({ ok: false, status: 500 }), held: () => new Set(), name: s => s, lang: () => "en", queue: async () => true, watchJob() {}, rerender() {} });
    await c.load(); expect(c.error()).toBe(true);
  });
});
