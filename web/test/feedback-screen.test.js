// T27: the Feedback screen. Posting shows Received at once, asks show a status and the Bengali read-back,
// the owner sees Approve and Decline, the father never does. Behaviour against fixtures, no real browser.
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import "../public/screens/feedback.js";
const F = globalThis.SPFeedback;
const fx = n => JSON.parse(readFileSync(new URL(`../../tests/fixtures/live/routes/${n}.json`, import.meta.url), "utf8"));
const list = () => JSON.parse(JSON.stringify(fx("feedback_list").response));
const t = (lang = "en") => k => (F.words[lang][k] ?? F.words.en[k] ?? k);

function server({ person = "father" } = {}) {
  const s = { calls: [], data: list(), person };
  s.fetch = async (url, o = {}) => {
    const method = o.method || "GET"; s.calls.push({ url, method, body: o.body && JSON.parse(o.body) });
    const ok = b => ({ ok: true, status: 200, json: async () => b });
    if (url === "/api/me") return ok({ person: s.person });
    if (url === "/api/v2/feedback" && method === "POST") {
      const id = "fb_new"; s.data.items.unshift({ id, person: s.person, text: JSON.parse(o.body).text, status: "received", created_at: "2026-11-26T09:00:00+05:30", asks: [] });
      return ok({ id, status: "received" });
    }
    if (url === "/api/v2/feedback") return ok(s.data);
    const m = url.match(/^\/api\/v2\/asks\/(.+)\/(not-meant|decide)$/);
    if (m) {
      const a = s.data.items.flatMap(i => i.asks).find(x => x.id === m[1]);
      if (m[2] === "not-meant") { a.not_meant = true; return ok({ id: a.id, not_meant: true }); }
      if (s.person !== "owner") return { ok: false, status: 403, json: async () => ({}) };
      a.status = JSON.parse(o.body).decision === "approve" ? "being_built" : "declined"; return ok({ id: a.id, status: a.status });
    }
    return { ok: false, status: 404, json: async () => ({}) };
  };
  return s;
}
const make = (s, extra = {}) => {
  const out = { html: "", timers: [] };
  const sc = F.createScreen({ fetch: s.fetch, t: t(extra.lang), lang: () => extra.lang || "en", paint: h => { out.html = h; },
    setTimeout: (fn, ms) => { out.timers.push({ fn, ms }); return out.timers.length; }, clearTimeout: () => {}, alive: () => true });
  out.sc = sc; return out;
};

describe("feedback screen", () => {
  it("shows a posted item at once as Received, and after a reload from the server", async () => {
    const s = server(); const o = make(s); await o.sc.start();
    await o.sc.post("show volume under the chart");
    expect(o.html).toContain("show volume under the chart");
    expect(o.html).toContain(F.words.en.stReceived);
    const o2 = make(s); await o2.sc.start();   // a reload: a new screen reads the server list
    expect(o2.html).toContain("show volume under the chart");
  });
  it("posts nothing when the box is empty", async () => {
    const s = server(); const o = make(s); await o.sc.start();
    await o.sc.post("   "); expect(s.calls.some(c => c.method === "POST")).toBe(false);
  });
  it("shows the status of each ask and the Bengali read-back", async () => {
    const s = server(); const o = make(s, { lang: "bn" }); await o.sc.start();
    expect(o.html).toContain("চার্টটা Kite-এর মতো করো");
    expect(o.html).toContain(F.words.bn.stBuilt);
    expect(o.html).toContain(F.words.bn.stWaiting);
    expect(o.html).toContain(F.words.bn.notMeant);
  });
  it("statuses change live: the next poll shows the new status", async () => {
    const s = server(); const o = make(s); await o.sc.start();
    expect(o.html).toContain(F.words.en.stBuilt);
    s.data.items[0].asks[0].status = "done";
    await o.timers.at(-1).fn();
    expect(o.html).toContain(F.words.en.stDone);
    expect(o.html).not.toContain(`data-st="being_built"`);
  });
  it("polls faster while something is still being read, slower when quiet", async () => {
    const s = server(); const o = make(s); await o.sc.start();
    const quiet = o.timers.at(-1).ms;
    await o.sc.post("x");
    expect(o.timers.at(-1).ms).toBeLessThan(quiet);
  });
  it("the father never sees Approve or Decline", async () => {
    const s = server({ person: "father" }); const o = make(s); await o.sc.start();
    expect(o.html).toContain(F.words.en.stWaiting);
    expect(o.html).not.toMatch(/data-fb-act="(approve|decline)"/);
  });
  it("the owner sees Approve and Decline on asks waiting for approval, and they work", async () => {
    const s = server({ person: "owner" }); const o = make(s); await o.sc.start();
    expect((o.html.match(/data-fb-act="approve"/g) || []).length).toBe(1);
    expect((o.html.match(/data-fb-act="decline"/g) || []).length).toBe(1);
    await o.sc.act("approve", "ask_002");
    expect(s.calls.at(-2).url).toBe("/api/v2/asks/ask_002/decide");
    expect(o.html).not.toMatch(/data-fb-act="approve"/);
  });
  it("Not what I meant flags the ask", async () => {
    const s = server(); const o = make(s); await o.sc.start();
    await o.sc.act("notmeant", "ask_001");
    expect(s.calls.some(c => c.url === "/api/v2/asks/ask_001/not-meant" && c.method === "POST")).toBe(true);
    expect(o.html).toContain(F.words.en.notMeantOn);
  });
  it("a failed post keeps the text and says it was not sent", async () => {
    const s = server(); const o = make(s); await o.sc.start();
    const f = s.fetch; s.fetch = async (u, op) => (op && op.method === "POST" ? { ok: false, status: 500, json: async () => ({}) } : f(u, op));
    const o3 = F.createScreen({ fetch: s.fetch, t: t(), lang: () => "en", paint: h => { o.html = h; }, setTimeout: () => 0, clearTimeout: () => {}, alive: () => true });
    await o3.start(); const r = await o3.post("hello"); expect(r).toBe(false);
    expect(o.html).toContain(F.words.en.notSent);
  });
  it("escapes what people type", async () => {
    const s = server(); s.data.items[0].text = "<img src=x onerror=1>"; const o = make(s); await o.sc.start();
    expect(o.html).not.toContain("<img src=x");
  });
  it("every English word has Bengali, and Bengali sentences contain Bengali letters", () => {
    expect(Object.keys(F.words.en).filter(k => !(k in F.words.bn))).toEqual([]);
    for (const [k, v] of Object.entries(F.words.en)) if (typeof v === "string" && v.split(/\s+/).length >= 4) expect(/[ঀ-৿]/.test(F.words.bn[k]), k).toBe(true);
  });
});
