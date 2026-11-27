// AUDIT #19: the yellow notification. A list update or a changed prediction must light a menu item and show on Today until seen.
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const ctx = { Intl, Date, console }; ctx.globalThis = ctx;
vm.runInNewContext(readFileSync(new URL("../public/screens/changes.js", import.meta.url), "utf8"), ctx);
const C = ctx.SPChanges;
const t = (k, ...a) => { const v = C.words.en[k]; return typeof v === "function" ? v(...a) : v; };
const tb = (k, ...a) => { const v = C.words.bn[k]; return typeof v === "function" ? v(...a) : v; };

const call = { id: "c1", person: "father", symbol: "FIXA", kind: "call_changed", old_value: "hold", new_value: "buy", reason: "Order win lifts the chance.", reason_bn: "অর্ডার জয়।", at: "2026-11-25T10:00:00+05:30", seen_at: null };
const entered = { id: "c2", person: "father", symbol: "FIXB", kind: "list_entered", old_value: null, new_value: "worth_following", reason: "Joined Worth following.", reason_bn: null, at: "2026-11-25T09:00:00+05:30", seen_at: null };
const left = { id: "c3", person: "father", symbol: "FIXC", kind: "list_left", old_value: "watchlist", new_value: null, reason: "Left the watchlist.", reason_bn: null, at: "2026-11-25T08:00:00+05:30", seen_at: null };

describe("which menu item gets a yellow dot", () => {
  it("a changed call lights Today, a list change lights the list's own tab, feedback lights Feedback", () => {
    expect(C.dotsOf([call, entered, left, { ...call, id: "c4", kind: "ask_status", symbol: "feedback" }])).toEqual({ today: 1, follow: 1, watchlist: 1, feedback: 1 });
  });
  it("seen changes and kinds with no tab earn no dot", () => {
    expect(C.dotsOf([{ ...call, seen_at: "2026-11-25T11:00:00+05:30" }, { ...call, id: "x", kind: "something_else" }])).toEqual({});
  });
  it("opening a tab picks exactly that tab's unseen changes", () => {
    expect(C.idsForTab([call, entered, left], "follow")).toEqual(["c2"]);
    expect(C.idsForTab([call, entered, left], "watchlist")).toEqual(["c3"]);
  });
});

describe("the What changed strip on Today", () => {
  const o = { t, lang: "en", name: s => s };
  it("shows what changed, from and to, why and when, and a way to clear it", () => {
    const h = C.stripHtml([call, entered, left], o);
    expect(h).toContain("What changed"); expect(h).toContain("3 changes since you last looked");
    expect(h).toContain("<b>hold</b> → <b>buy</b>"); expect(h).toContain("Order win lifts the chance.");
    expect(h).toContain("Worth following"); expect(h).toContain("Watchlist"); expect(h).toContain("data-chg-all");
    expect(h).toContain("25 Nov, 10:00");
  });
  it("is empty when everything is seen, and caps at five lines with a count of the rest", () => {
    expect(C.stripHtml([{ ...call, seen_at: "x" }], o)).toBe("");
    const many = Array.from({ length: 7 }, (_, i) => ({ ...call, id: "m" + i }));
    const h = C.stripHtml(many, o);
    expect((h.match(/class="chg-li"/g) || []).length).toBe(5); expect(h).toContain("and 2 more");
  });
  it("reads in Bengali with the Bengali reason when there is one, and has no English sentence left", () => {
    const h = C.stripHtml([call], { t: tb, lang: "bn", name: s => s });
    expect(h).toContain("অর্ডার জয়।"); expect(h).toContain("যা বদলেছে"); expect(h).not.toContain("What changed");
  });
  it("escapes what the server sent", () => {
    expect(C.stripHtml([{ ...call, reason: "<img src=x onerror=1>" }], o)).not.toContain("<img");
  });
});
