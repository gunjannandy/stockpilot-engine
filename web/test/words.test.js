// T30: every fixed English screen word needs hand-written Bengali, or the build fails.
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import vm from "node:vm";

// Run app.js against a stub page that never finishes loading, so only the word tables are built.
function loadWords() {
  const src = readFileSync(new URL("../public/app.js", import.meta.url), "utf8");
  const noop = () => {};
  const doc = { readyState: "loading", addEventListener: noop, querySelector: () => null, querySelectorAll: () => [], documentElement: { dataset: {} }, body: {} };
  const win = { SP_WORDS: null };
  const ctx = { window: win, document: doc, localStorage: { getItem: () => null, setItem: noop }, matchMedia: () => ({ matches: false }), location: { hash: "" }, console, addEventListener: noop, removeEventListener: noop, setTimeout: noop, requestAnimationFrame: noop, innerWidth: 1280, navigator: {}, fetch: () => new Promise(noop) };
  win.window = win;
  // T22: the stock screen's own words live in screens/stock.js; app.js merges them, so the gate loads that file first.
  vm.runInNewContext(readFileSync(new URL("../public/screens/stock.js", import.meta.url), "utf8"), ctx);
  vm.runInNewContext(src, ctx);
  vm.createContext(ctx);
  vm.runInContext(readFileSync(new URL("../public/screens/worth.js", import.meta.url), "utf8"), ctx);   // screens add their words first
  vm.runInContext(readFileSync(new URL("../public/screens/changes.js", import.meta.url), "utf8"), ctx);   // AUDIT #19
  vm.runInContext(readFileSync(new URL("../public/screens/news-live.js", import.meta.url), "utf8"), ctx);   // AUDIT #23
  vm.runInContext(src, ctx);
  return win.SP_WORDS;
}

const hasBn = t => /[ঀ-৿]/.test(t);
// Words that read the same in both languages: trade words and names stay in English letters.
const SAME_OK = /^[\d\s.,%₹+−–\-/()&:'"A-Za-z]*$/;

describe("fixed screen words", () => {
  const W = loadWords();

  it("has a Bengali string for every English key", () => {
    const missing = Object.keys(W.en).filter(k => !(k in W.bn));
    expect(missing).toEqual([]);
  });

  it("every Bengali sentence contains Bengali letters (trade words alone may stay English)", () => {
    const bad = [];
    for (const [k, v] of Object.entries(W.en)) {
      if (typeof v !== "string" || v.split(/\s+/).length < 4) continue;   // one to three words are trade words or names
      const b = W.bn[k];
      if (typeof b === "string" && !hasBn(b)) bad.push(k);
    }
    expect(bad).toEqual([]);
  });

  it("the father's examples of untranslated sentences are covered", () => {
    // Sentences he still saw in English after switching to Bengali (feedback 5), taken from the live en table.
    const sentences = Object.entries(W.en).filter(([, v]) => typeof v === "string" && v.split(/\s+/).length >= 4);
    expect(sentences.length).toBeGreaterThan(20);
    for (const [k] of sentences) expect(hasBn(W.bn[k] ?? ""), k).toBe(true);
  });

  it("sentence-building functions give Bengali too", () => {
    const bad = [];
    for (const [k, f] of Object.entries(W.en)) {
      if (typeof f !== "function") continue;
      const g = W.bn[k];
      if (typeof g !== "function") { bad.push(k + " (not a function in bn)"); continue; }
      try { const outs = [[3, "Reliance", true], ["sell", "Reliance", true], [2, 1, 1]].map(a => { try { return String(g(...a)); } catch { return ""; } }); if (outs.some(Boolean) && !outs.some(hasBn)) bad.push(k); } catch { /* needs data we do not stub */ }
    }
    expect(bad).toEqual([]);
  });
});
