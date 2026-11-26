// MAINCHECK: the merged shell keeps every screen reachable and has no leftover duplicate lines.
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";

const read = p => readFileSync(new URL(`../public/${p}`, import.meta.url), "utf8");
const html = read("index.html"), app = read("app.js");

describe("merged shell", () => {
  it("loads each script and stylesheet once", () => {
    const refs = [...html.matchAll(/<(?:script src|link rel="stylesheet" href)="([^"]+)"/g)].map(m => m[1]);
    const fonts = refs.filter(r => r.includes("fonts.googleapis.com/css2?family=Material+Symbols"));
    expect(fonts.length).toBe(1);
    const dup = refs.filter((r, i) => refs.indexOf(r) !== i);
    expect(dup).toEqual([]);
  });

  it("the one icon font lists every icon the screens use", () => {
    const list = decodeURIComponent(html.match(/icon_names=([^&"]+)/)[1]).split(",");
    const used = new Set();
    for (const f of ["app.js", "screens/stock.js", "screens/universe.js", "screens/worth.js", "screens/jobs.js", "screens/feedback.js", "screens/records.js", "live.js"]) {
      for (const m of read(f).matchAll(/class="ms[^"]*"[^>]*>\s*([a-z_]+)\s*</g)) used.add(m[1]);
    }
    for (const m of app.matchAll(/NAV2?(?:\.push|\.unshift)?\(?\s*=?\s*\[?\[("[a-z]+", "([a-z_]+)"(?:, "[a-z]+")?\](?:, )?)+/g)) for (const n of m[0].matchAll(/\["[a-z]+", "([a-z_]+)"/g)) used.add(n[1]);
    expect([...used].filter(i => !list.includes(i))).toEqual([]);
  });

  it("the side menu lists Every stock, Worth following, Holdings and Today", () => {
    const nav = app.split("NAV.length = 0;")[1].split("\n")[1];
    for (const k of ["today", "holdings", "follow", "universe", "watchlist"]) expect(nav).toContain(`["${k}"`);
  });

  it("the toast area has each attribute once", () => {
    expect(app).not.toMatch(/role="status" aria-live="polite" role="status"/);
  });
});

describe("owner feedback #3 and #4", () => {
  it("Today draws the calls-date note as its own banner above the headline", () => {
    expect(app).toContain("SPRecords.callsBanner(D.today, S.lang)");
    expect(app.indexOf("${banner}<header class=\"lead\">")).toBeGreaterThan(0);
  });
  it("a stock back from snooze shows a label in both languages", () => {
    expect(app.match(/backSnooze: "/g).length).toBe(2);
    expect(app).toContain("D.settings?.back_from_snooze");
  });
});
