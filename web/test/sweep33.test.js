// T33: defects the click sweep found (web/tests/e2e-t33.mjs). Source-level checks; the browser sweep proves the rest.
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
const read = p => readFileSync(new URL(`../public/${p}`, import.meta.url), "utf8");
const app = read("app.js"), css = read("app.css");

describe("phone bottom bar (400 px)", () => {
  const navLine = app.split("NAV.length = 0;")[1].split("\n")[1];
  const bar = [...navLine.matchAll(/\["([a-z]+)", "[a-z_]+"(?:, "(desk)")?\]/g)].filter(m => !m[2]).map(m => m[1]);
  it("shows at most five routes plus More, so More is on screen", () => { expect(bar.length).toBeLessThanOrEqual(5); });
  it("More lists every route the bar leaves out", () => {
    const more = app.split("openMore = function")[1].split("\n")[1];
    const all = [...navLine.matchAll(/\["([a-z]+)", "[a-z_]+"(?:, "(desk)")?\]/g)].filter(m => m[2]).map(m => m[1]);
    for (const k of all) expect(more).toContain(`["${k}"`);
  });
});

describe("side rail (1100 px, short window)", () => {
  it("scrolls when its items are taller than the window", () => {
    const rule = css.split("\n").find(l => /^#rail\{/.test(l));
    expect(rule).toMatch(/overflow-y:\s*auto/);
  });
});

describe("watchlist add box (400 px)", () => {
  it("its result list opens leftwards on a phone so the page does not scroll sideways", () => {
    const phone = css.split("@media (max-width:700px)").slice(1).join("\n");
    expect(phone).toMatch(/\.wlr\{[^}]*right:\s*0/);
  });
});
