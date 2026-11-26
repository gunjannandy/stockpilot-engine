// BROWSERFIX: a browser that rejects a language tag must not blank the screen.
import { describe, it, expect } from "vitest";
import "../public/locale-guard.js";

const bad = tag => /^bn/.test(tag || "");
// A stand-in global: formatters that throw for "bn..." the way a thin ICU build does.
function fakeGlobal() {
  const boom = () => { throw new RangeError("Incorrect locale information provided"); };
  const mk = () => ({ toLocaleDateString(l) { if (bad(l)) boom(); return "date:" + l; }, toLocaleString(l) { if (bad(l)) boom(); return "num:" + l; }, toLocaleTimeString(l) { if (bad(l)) boom(); return "t:" + l; } });
  function DTF(l) { if (bad(l)) boom(); this.l = l; }
  DTF.supportedLocalesOf = () => [];
  return { Date: { prototype: mk() }, Number: { prototype: { toLocaleString: mk().toLocaleString } }, String: { prototype: { localeCompare(a, b) { if (bad(a)) boom(); return 0; } } }, Intl: { DateTimeFormat: DTF } };
}

describe("locale guard", () => {
  it("falls back to English when the language tag is rejected, and leaves good tags alone", () => {
    const g = fakeGlobal(); globalThis.SPLocaleGuard.install(g);
    expect(g.Date.prototype.toLocaleDateString("bn-IN-u-nu-latn")).toBe("date:en-IN");
    expect(g.Date.prototype.toLocaleDateString("en-GB")).toBe("date:en-GB");
    expect(g.Number.prototype.toLocaleString("bn-IN")).toBe("num:en-IN");
    expect(new g.Intl.DateTimeFormat("bn-IN").l).toBe("en-IN");
  });
  it("does not hide a real error", () => {
    const g = fakeGlobal(); g.Date.prototype.toLocaleDateString = function () { throw new TypeError("x"); };
    globalThis.SPLocaleGuard.install(g);
    expect(() => g.Date.prototype.toLocaleDateString("en-IN")).toThrow(TypeError);
  });
  it("is loaded before every other script on the page", () => {
    return import("node:fs").then(({ readFileSync }) => {
      const html = readFileSync(new URL("../public/index.html", import.meta.url), "utf8");
      expect(html.indexOf("locale-guard.js")).toBeGreaterThan(-1);
      expect(html.indexOf("locale-guard.js")).toBeLessThan(html.indexOf("<script src=\"vendor/"));
    });
  });
});
