// T23: Fuse.js search over the full index. Neutral ids only; no private data.
import { describe, it, expect } from "vitest";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const Fuse = require("fuse.js");
await import("../public/search.js");
const { createSearch } = globalThis.SPSearch;

const WORDS = ["Alpha", "Bharat", "Coastal", "Delta", "Eastern", "Fortune", "Global", "Hindustan", "Indo", "Jupiter", "Kaveri", "Lotus", "Metro", "Nova", "Orient", "Prime", "Quest", "Royal", "Sagar", "Titan"];
const SUFFIX = ["Industries", "Textiles", "Pharma", "Steel", "Foods", "Power", "Motors", "Chemicals", "Finance", "Realty"];
function bigIndex() {
  const entries = [{ symbol: "ANAWIL", exchange: "NSE", segment: "NSE_SME", name: "Anand Widgets Limited", isin: "INE0AAA01010", aliases: ["anand widgets", "anawil"] }];
  for (let i = 0; entries.length < 9000; i++) {
    const name = `${WORDS[i % 20]} ${SUFFIX[Math.floor(i / 20) % 10]} ${i} Limited`;
    const symbol = (WORDS[i % 20].slice(0, 4) + SUFFIX[Math.floor(i / 20) % 10].slice(0, 3) + i).toUpperCase();
    entries.push({ symbol, exchange: i % 3 ? "NSE" : "BSE", segment: i % 3 ? "NSE" : "BSE", name, isin: "INE" + String(i).padStart(9, "0"), aliases: [name.toLowerCase().replace(" limited", ""), symbol.toLowerCase()] });
  }
  return entries;
}

describe("search", () => {
  const s = createSearch(Fuse, bigIndex());
  it("finds ANAWIL from a misspelt symbol", () => {
    for (const q of ["anawill", "annawil", "anwil", "ANAWIL"]) expect(s.find(q).map(r => r.symbol)).toContain("ANAWIL");
  });
  it("finds ANAWIL from a misspelt name", () => {
    for (const q of ["anand widgts", "anad widgets", "Anand Widgets"]) expect(s.find(q)[0].symbol).toBe("ANAWIL");
  });
  it("an exact symbol comes first", () => { expect(s.find("anawil")[0].symbol).toBe("ANAWIL"); });
  it("held and watched stocks rank above equal matches", () => {
    const r = createSearch(Fuse, bigIndex(), { boost: sym => (sym === "ALPHIND1800" ? 1 : 0) });
    expect(r.find("alpha industries")[0].symbol).toBe("ALPHIND1800");
  });
  it("answers within 100 ms on the full index", () => {
    s.find("warm");
    const t = performance.now();
    for (const q of ["anawil", "coastal pharma", "titn steel", "rel"]) s.find(q);
    expect((performance.now() - t) / 4).toBeLessThan(100);
  });
  it("returns nothing for an empty query and caps results", () => {
    expect(s.find("  ")).toEqual([]);
    expect(s.find("a").length).toBeLessThanOrEqual(8);
  });
});
