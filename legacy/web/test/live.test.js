// T21: data client, polling rules, job progress and notification rules N1-N9. Behaviour only, no look.
import { describe, it, expect, beforeEach } from "vitest";
import { readFileSync } from "node:fs";
import "../public/live.js";   // a plain browser script: it puts SPLive on the global
const L = globalThis.SPLive;
const fx = n => JSON.parse(readFileSync(new URL(`../../tests/fixtures/live/routes/${n}.json`, import.meta.url), "utf8")).response;

// A fake browser: a clock, timers, tab visibility, and a server that remembers marks per person.
function world({ person = "father" } = {}) {
  const w = { t: 0, timers: [], hidden: false, calls: [], listeners: {}, titleSet: [], badge: [], jobStatus: "running" };
  const marks = { father: JSON.parse(JSON.stringify(fx("changes_list"))), owner: JSON.parse(JSON.stringify(fx("changes_list"))) };
  marks.owner.person = "owner"; marks.owner.items[0].person = "owner";
  w.setTimeout = (fn, ms) => { const id = w.timers.length + 1; w.timers.push({ id, fn, at: w.t + ms, on: true }); return id; };
  w.clearTimeout = id => { const x = w.timers.find(t => t.id === id); if (x) x.on = false; };
  // Step the clock a second at a time and let promises settle, as a real browser does between timers.
  w.advance = async ms => { for (let done = 0; done < ms; done += 1000) { const end = w.t + Math.min(1000, ms - done); for (;;) { const nx = w.timers.filter(t => t.on && t.at <= end).sort((a, b) => a.at - b.at)[0]; if (!nx) break; nx.on = false; w.t = nx.at; nx.fn(); } w.t = end; for (let i = 0; i < 10; i++) await Promise.resolve(); } };
  w.fetch = async (url, opts = {}) => {
    w.calls.push({ url, method: opts.method || "GET", t: w.t });
    const ok = b => ({ ok: true, status: 200, json: async () => b });
    if (url.startsWith("/api/v2/changes/seen")) {
      const b = JSON.parse(opts.body); let n = 0;
      marks[person].items.forEach(i => { if (!i.seen_at && (b.all || (b.symbol && i.symbol === b.symbol) || (b.ids || []).includes(i.id))) { i.seen_at = "x"; n++; } });
      marks[person].unseen_count = marks[person].items.filter(i => !i.seen_at).length;
      return ok({ marked: n });
    }
    if (url.startsWith("/api/v2/changes")) return ok(JSON.parse(JSON.stringify(marks[person])));
    if (url.startsWith("/api/v2/jobs/")) { const j = fx("jobs_get"); j.job.status = w.jobStatus; if (w.jobStatus === "done") j.job.result = "Done, 1 change"; return ok(j); }
    return { ok: false, status: 404, json: async () => ({}) };
  };
  w.doc = { get hidden() { return w.hidden; }, addEventListener: (e, f) => { (w.listeners[e] ||= []).push(f); }, set title(v) { w.titleSet.push(v); }, get title() { return w.titleSet.at(-1) ?? "stockpilot"; } };
  w.show = () => { w.hidden = false; (w.listeners.visibilitychange || []).forEach(f => f()); };
  w.hide = () => { w.hidden = true; (w.listeners.visibilitychange || []).forEach(f => f()); };
  w.marks = marks;
  return w;
}
const mk = (w, o = {}) => L.createClient({ fetch: w.fetch, document: w.doc, setTimeout: w.setTimeout, clearTimeout: w.clearTimeout, now: () => w.t, person: "father", ...o });
const flush = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };

describe("marks (N1, N2, N3)", () => {
  it("a fixture change gives the row dot, the nav count and the tab badge", async () => {
    const w = world(); const c = mk(w); await c.refreshChanges();
    expect(c.hasDot("FIXA")).toBe(true);
    expect(c.hasDot("FIXB")).toBe(false);
    expect(c.navCounts()).toEqual({ calls: 1 });
    expect(c.tabTitle("stockpilot")).toBe("(1) stockpilot");
    expect(w.doc.title).toBe("(1) stockpilot");
    expect(decodeURIComponent(c.badgeHref())).toContain("1");
  });
  it("opening the row clears the dot, the count and the badge for that person only", async () => {
    const w = world(); const c = mk(w); await c.refreshChanges();
    await c.openStock("FIXA");
    expect(c.hasDot("FIXA")).toBe(false);
    expect(c.navCounts()).toEqual({});
    expect(w.doc.title).toBe("stockpilot");
    const other = world({ person: "owner" }); other.marks.owner = w.marks.owner; // owner's own marks sit untouched
    const oc = mk(other, { person: "owner" }); await oc.refreshChanges();
    expect(oc.hasDot("FIXA")).toBe(true);
    expect(w.marks.owner.items[0].seen_at).toBeNull();
  });
  it("sends the seen call to the server", async () => {
    const w = world(); const c = mk(w); await c.refreshChanges(); await c.openStock("FIXA");
    expect(w.calls.some(x => x.method === "POST" && x.url === "/api/v2/changes/seen")).toBe(true);
  });
  it("Mark all seen clears every mark", async () => {
    const w = world(); const c = mk(w); await c.refreshChanges(); await c.markAllSeen();
    expect(c.unseenCount()).toBe(0);
  });
  it("the What changed strip drops changes older than 7 days but not unseen recent ones", () => {
    const now = Date.parse("2026-11-25T12:00:00+05:30");
    const mkItem = (id, at, seen) => ({ id, symbol: id, kind: "call_changed", at, seen_at: seen ? "x" : null });
    const s = L.stripItems([mkItem("A", "2026-11-24T09:00:00+05:30"), mkItem("B", "2026-11-10T09:00:00+05:30"), mkItem("C", "2026-11-25T09:00:00+05:30", true)], now);
    expect(s.map(x => x.id)).toEqual(["A"]);
  });
  it("only decision-relevant kinds count; nav sends list moves to Lists and ask status to Feedback", () => {
    const items = [{ kind: "list_entered", symbol: "A" }, { kind: "ask_status", symbol: "B" }, { kind: "chance_moved", symbol: "C" }, { kind: "bogus", symbol: "D" }];
    expect(L.navCountsOf(items)).toEqual({ lists: 1, feedback: 1, calls: 1 });
  });
});

describe("polling rules", () => {
  it("polls every 5 minutes while visible", async () => {
    const w = mk0(); const c = w.c; c.start(); await flush();
    const n0 = w.w.calls.filter(x => x.url.startsWith("/api/v2/changes?")).length;
    await w.w.advance(5 * 60 * 1000 + 10); await flush();
    expect(w.w.calls.filter(x => x.url.startsWith("/api/v2/changes?")).length).toBe(n0 + 1);
  });
  it("does no polling while the tab is hidden", async () => {
    const { w, c } = mk0(); c.start(); await flush(); w.hide();
    c.watchJob("job_002");
    const before = w.calls.length;
    await w.advance(30 * 60 * 1000); await flush();
    expect(w.calls.length).toBe(before);
  });
  it("refreshes once when the tab comes to the front, and resumes the 5 minute rhythm", async () => {
    const { w, c } = mk0(); c.start(); await flush(); w.hide(); await w.advance(20 * 60 * 1000);
    const before = w.calls.length; w.show(); await flush();
    expect(w.calls.length).toBeGreaterThan(before);
    const b2 = w.calls.length; await w.advance(5 * 60 * 1000 + 10); await flush();
    expect(w.calls.length).toBeGreaterThan(b2);
  });
  it("polls a running job every few seconds and stops when it is done, then toasts", async () => {
    const { w, c } = mk0(); const events = []; c.on(e => events.push(e)); c.start(); await flush();
    c.watchJob("job_002"); await flush();
    const jobCalls = () => w.calls.filter(x => x.url === "/api/v2/jobs/job_002").length;
    await w.advance(9000); await flush();
    expect(jobCalls()).toBeGreaterThanOrEqual(3);
    w.jobStatus = "done"; await w.advance(4000); await flush();
    const n = jobCalls(); await w.advance(30000); await flush();
    expect(jobCalls()).toBe(n);
    const t = events.find(e => e.type === "toast");
    expect(t.text).toMatch(/ready/i); expect(t.action).toBe("Open"); expect(t.ms).toBe(8000);
  });
  it("a failed job toasts plain words and Try again", async () => {
    const { w, c } = mk0(); const events = []; c.on(e => events.push(e)); w.jobStatus = "failed"; c.watchJob("job_002"); await w.advance(4000); await flush();
    const t = events.find(e => e.type === "toast");
    expect(t.action).toBe("Try again");
  });
  it("a job being watched while hidden catches up when the tab returns", async () => {
    const { w, c } = mk0(); c.start(); w.hide(); c.watchJob("job_002"); await flush();
    const b = w.calls.filter(x => x.url === "/api/v2/jobs/job_002").length; expect(b).toBe(0);
    w.show(); await flush();
    expect(w.calls.filter(x => x.url === "/api/v2/jobs/job_002").length).toBeGreaterThan(0);
  });
});
function mk0() { const w = world(); return { w, c: mk(w) }; }

describe("job progress component", () => {
  it("renders lines in order with plain state words, Bengali when chosen", () => {
    const j = fx("jobs_get");
    const en = L.jobProgressHtml(j, "en"), bn = L.jobProgressHtml({ job: j.job, lines: [{ ...j.lines[0], text_bn: "সংখ্যা পড়ছি" }] }, "bn");
    expect(en).toContain("Reading the numbers"); expect(bn).toContain("সংখ্যা পড়ছি");
    expect(en).toContain('data-state="running"');
  });
  it("escapes text and shows the failure in plain words", () => {
    const h = L.jobProgressHtml({ job: { status: "failed", error: "Could not <b>read</b>" }, lines: [] }, "en");
    expect(h).not.toContain("<b>read"); expect(h).toContain("Try again");
  });
});

describe("other marks", () => {
  it("newspaper icon: news without change shows an icon with Update, never a dot", () => {
    const r = L.rowMarks({ dot: false, newsNoChange: true });
    expect(r).toContain("newspaper"); expect(r).toContain("Update"); expect(r).not.toContain("dot");
  });
  it("yellow band on a changed stock states time, old to new, chance change and reason", () => {
    const h = L.changeBandHtml({ at: "2026-11-25T09:15:00+05:30", old_value: "hold", new_value: "buy", reason: "Profit growth beat the usual", kind: "call_changed" });
    expect(h).toContain("hold"); expect(h).toContain("buy"); expect(h).toContain("Profit growth"); expect(h).toContain("25 Nov");
  });
  it("out-of-date forecast is an amber chip, not a dot", () => {
    const h = L.staleChip(true); expect(h).toContain("amber"); expect(h).not.toContain("dot"); expect(L.staleChip(false)).toBe("");
  });
  it("the red Health count shows only to the owner", () => {
    expect(L.healthCount(3, "owner")).toBe(3);
    expect(L.healthCount(3, "father")).toBe(0);
  });
});

describe("near-live price with its age (T15)", () => {
  const q = (age, extra = {}) => ({ symbol: "FIXB", exchange: "NSE", price: 104.5, prev_close: 101, as_of: "x", source: "yahoo", age_seconds: age, ...extra });
  it("always says how old the price is, in plain words", () => {
    expect(L.priceLabel(q(20))).toBe("price just now");
    expect(L.priceLabel(q(14 * 60 + 5))).toBe("price 14 min old");
    expect(L.priceLabel(q(14 * 60), true)).toBe("price 14 min old · refreshing");
    expect(L.priceLabel(q(3 * 3600))).toBe("price 3 h old");
    expect(L.priceLabel(q(2 * 86400))).toBe("price 2 days old");
    expect(L.priceLabel(null, true)).toBe("price not available yet · refreshing");
    expect(L.priceLabel(null)).toBe("price not available yet");
  });
  function priceWorld(ages) {
    const w = world(); const calls = [];
    const base = w.fetch;
    w.fetch = async (url, o) => {
      if (!url.startsWith("/api/v2/quotes")) return base(url, o);
      w.calls.push({ url, t: w.t });
      const refresh = url.includes("refresh=1");
      return { ok: true, status: 200, json: async () => ({ quotes: [q(refresh ? ages.fresh : ages.stored)] }) };
    };
    return w;
  }
  it("opening a stock shows the stored price at once as refreshing, then swaps in the refreshed one", async () => {
    const w = priceWorld({ stored: 14 * 60, fresh: 30 }); const c = mk(w); const seen = [];
    c.on(e => { if (e.type === "quote") seen.push([L.priceLabel(e.quote, e.refreshing), e.refreshing]); });
    c.openQuote("FIXB"); await flush();
    expect(seen).toEqual([["price 14 min old · refreshing", true], ["price just now", false]]);
    expect(w.calls.filter(x => x.url.includes("refresh=1")).length).toBe(1);
  });
  it("keeps the old price and says so when the refresh fails", async () => {
    const w = priceWorld({ stored: 600, fresh: 600 }); const f = w.fetch;
    w.fetch = async (u, o) => u.includes("refresh=1") ? { ok: false, status: 500, json: async () => ({}) } : f(u, o);
    const c = mk(w); const seen = []; c.on(e => { if (e.type === "quote") seen.push([L.priceLabel(e.quote, e.refreshing), e.refreshing]); });
    c.openQuote("FIXB"); await flush();
    expect(seen.at(-1)).toEqual(["price 10 min old", false]);
  });
  it("asks again every 5 minutes while the stock stays open and the tab is visible, and stops when closed or hidden", async () => {
    const w = priceWorld({ stored: 60, fresh: 30 }); const c = mk(w);
    c.openQuote("FIXB"); await flush();
    const n0 = w.calls.filter(x => x.url.includes("refresh=1")).length;
    await w.advance(5 * 60 * 1000); await flush();
    expect(w.calls.filter(x => x.url.includes("refresh=1")).length).toBe(n0 + 1);
    w.hide(); await w.advance(20 * 60 * 1000);
    expect(w.calls.filter(x => x.url.includes("refresh=1")).length).toBe(n0 + 1);
    w.show(); await flush();
    expect(w.calls.filter(x => x.url.includes("refresh=1")).length).toBe(n0 + 2);
    c.closeQuote(); await w.advance(10 * 60 * 1000);
    expect(w.calls.filter(x => x.url.includes("refresh=1")).length).toBe(n0 + 2);
  });
});
