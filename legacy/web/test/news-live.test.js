// AUDIT #23: the live news block says what happened, how old it is, and which stocks it touches, in both languages.
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const ctx = { Date, console }; ctx.globalThis = ctx;
vm.runInNewContext(readFileSync(new URL("../public/screens/news-live.js", import.meta.url), "utf8"), ctx);
const N = ctx.SPNewsLive;
const mk = l => (k, ...a) => { const v = N.words[l][k]; return typeof v === "function" ? v(...a) : v; };
const NOW = Date.parse("2026-11-26T10:00:00+05:30");
const item = (o = {}) => ({ id: "n1", link: "https://example.invalid/a?x=1&y=2", title: "Fixture Alpha wins a big order", source: "Example ET", published_at: "2026-11-26T09:52:00+05:30", source_count: 3, direction: "good", impact: 4,
  line_en: "Order win lifts profit.", line_bn: "অর্ডার জয়ে মুনাফা বাড়বে।", tags: [{ symbol: "FIXA", exchange: "NSE", relation: "self", direction: "good", size: "medium", changes_call: true }], rank: { tier: "high", score: 9, closeness: "holding" }, ...o });

describe("age words", () => {
  it("says just now, minutes, hours and days", () => {
    const t = mk("en");
    expect([30e3, 8 * 60e3, 3 * 3600e3, 2 * 86400e3].map(ms => N.ago(new Date(NOW - ms).toISOString(), NOW, t))).toEqual(["just now", "8 min ago", "3 h ago", "2 d ago"]);
  });
});
describe("the block", () => {
  const o = l => ({ t: mk(l), lang: l, now: NOW, name: s => "Name of " + s, held: s => s === "FIXA", checkedAt: NOW });
  it("shows the title as a link that opens the article, the one-line read, the age and the sources", () => {
    const h = N.blockHtml({ items: [item()] }, { items: [] }, o("en"));
    expect(h).toContain('href="https://example.invalid/a?x=1&amp;y=2"'); expect(h).toContain('target="_blank"'); expect(h).toContain("noopener");
    expect(h).toContain("Order win lifts profit."); expect(h).toContain("8 min ago"); expect(h).toContain("3 sources"); expect(h).toContain("Changes our view");
    expect(h).toContain("Newest item 8 min ago"); expect(h).toContain("checked just now");
  });
  it("names the stocks it touches as tappable chips, marking the one the owner holds", () => {
    const h = N.blockHtml({ items: [item()] }, { items: [] }, o("en"));
    expect(h).toContain('data-open="FIXA"'); expect(h).toContain("Name of FIXA"); expect(h).toContain("You hold it");
  });
  it("lists the In today's news stocks with why", () => {
    const h = N.blockHtml({ items: [] }, { items: [{ symbol: "FIXB", reason: "Order win.", reason_bn: "অর্ডার জয়।" }] }, o("en"));
    expect(h).toContain("In today&#39;s news"); expect(h).toContain('data-open="FIXB"'); expect(h).toContain("Order win.");
  });
  it("says so plainly when nothing has come in, or when the news could not load", () => {
    expect(N.blockHtml({ items: [] }, { items: [] }, o("en"))).toContain("No news has come in yet");
    expect(N.blockHtml(null, null, o("en"))).toContain("did not load");
  });
  it("reads in Bengali, with the Bengali line, and no fixed English sentence", () => {
    const h = N.blockHtml({ items: [item()] }, { items: [] }, o("bn"));
    expect(h).toContain("অর্ডার জয়ে মুনাফা বাড়বে।"); expect(h).toContain("বাজারের খবর, সরাসরি"); expect(h).not.toContain("Market news, live"); expect(h).not.toContain("Changes our view");
  });
  it("escapes what the feeds sent", () => {
    expect(N.blockHtml({ items: [item({ title: "<img src=x onerror=1>" })] }, { items: [] }, o("en"))).not.toContain("<img");
  });
  it("shows at most eight items", () => {
    const h = N.blockHtml({ items: Array.from({ length: 12 }, (_, i) => item({ id: "n" + i })) }, { items: [] }, o("en"));
    expect((h.match(/class="nl-item"/g) || []).length).toBe(8);
  });
});
