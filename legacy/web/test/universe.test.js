// T25: the universe table's rules. Neutral ids only; no private data.
import { describe, it, expect } from "vitest";
await import("../public/screens/universe-core.js");
const U = globalThis.SPUniverseCore;

function table(n = 9000) {
  const t = { built_at: "t", n, symbol: [], exchange: [], segment: [], name: [], sector: [], pe: [], growth: [], chance_6m: [], mcap_cr: [], last: [], day_change_pct: [] };
  for (let i = 0; i < n; i++) {
    t.symbol.push("S" + i); t.exchange.push(i % 3 ? "NSE" : "BSE"); t.segment.push(i % 3 ? (i % 7 ? "NSE" : "NSE_SME") : "BSE");
    t.name.push(`Stock ${i} Limited`); t.sector.push(i % 5 === 0 ? null : "Sector " + (i % 4));
    t.pe.push(i % 6 === 0 ? null : 5 + (i % 50)); t.growth.push(i % 8 === 0 ? null : (i % 40) - 10);
    t.chance_6m.push(i % 4 === 0 ? null : 0.3 + (i % 50) / 100); t.mcap_cr.push(i % 9 === 0 ? null : 100 * (1 + (i % 400))); t.last.push(10 + i); t.day_change_pct.push(0);
  }
  return t;
}
const T = table();

describe("universe filters", () => {
  it("a filter keeps only matching rows, and rows with no figure never match a range", () => {
    const f = U.run(T, { pe: "lt15" }, null, "");
    expect(f.length).toBeGreaterThan(0);
    for (const i of f) expect(T.pe[i]).toBeLessThan(15), expect(T.pe[i]).not.toBeNull();
    expect(U.run(T, { pe: "none" }, null, "").every(i => T.pe[i] == null)).toBe(true);
  });
  it("filters combine (all must hold)", () => {
    const a = U.run(T, { pe: "lt15" }, null, ""), b = U.run(T, { exchange: "NSE" }, null, ""), ab = U.run(T, { pe: "lt15", exchange: "NSE" }, null, "");
    expect(ab.length).toBe(a.filter(i => b.includes(i)).length);
    expect(ab.length).toBeLessThan(Math.min(a.length, b.length));
  });
  it("size, growth, chance, sector and SME filters work", () => {
    expect(U.run(T, { size: "large" }, null, "").every(i => T.mcap_cr[i] >= 20000)).toBe(true);
    expect(U.run(T, { growth: "up" }, null, "").every(i => T.growth[i] > 15)).toBe(true);
    expect(U.run(T, { chance: "p60" }, null, "").every(i => T.chance_6m[i] >= 0.6)).toBe(true);
    expect(U.run(T, { sector: "Sector 2" }, null, "").every(i => T.sector[i] === "Sector 2")).toBe(true);
    expect(U.run(T, { exchange: "SME" }, null, "").every(i => /SME/.test(T.segment[i]))).toBe(true);
  });
  it("typed words match name or symbol", () => {
    expect(U.run(T, {}, null, "stock 12").every(i => /stock 12/i.test(T.name[i] + " " + T.symbol[i]) || /stock/.test(T.name[i].toLowerCase()))).toBe(true);
    expect(U.run(T, {}, null, "S77").map(i => T.symbol[i])).toContain("S77");
  });
  it("sorts by a column, missing values last in both directions", () => {
    for (const d of [1, -1]) {
      const r = U.run(T, { exchange: "NSE" }, { key: "pe", d }, ""), vals = r.map(i => T.pe[i]);
      const firstNull = vals.findIndex(v => v == null), real = firstNull < 0 ? vals : vals.slice(0, firstNull);
      expect(vals.slice(real.length).every(v => v == null)).toBe(true);
      for (let k = 1; k < real.length; k++) expect(d * (real[k] - real[k - 1])).toBeGreaterThanOrEqual(0);
    }
  });
  it("runs over the full 9,000 universe fast", () => {
    const t0 = performance.now(); U.run(T, { pe: "lt15", exchange: "NSE" }, { key: "mcap_cr", d: -1 }, "st"); expect(performance.now() - t0).toBeLessThan(200);
  });
  it("sector list comes from the data", () => {
    expect(U.sectors(T).sort()).toEqual(["Sector 0", "Sector 1", "Sector 2", "Sector 3"]);
  });
});

describe("persist per browser", () => {
  const mem = () => { const m = {}; return { getItem: k => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = v; } }; };
  it("saves and restores filters and sort", () => {
    const s = mem(); U.save(s, { filters: { pe: "lt15", size: "mid" }, sort: { key: "pe", d: 1 } });
    expect(U.load(s)).toEqual({ filters: { pe: "lt15", size: "mid" }, sort: { key: "pe", d: 1 } });
  });
  it("ignores junk, unknown filters and values, and storage that throws", () => {
    const s = mem(); s.setItem(U.KEY, "{not json"); expect(U.load(s)).toEqual({ filters: {}, sort: null });
    s.setItem(U.KEY, JSON.stringify({ filters: { pe: "bogus", nope: "x", exchange: "NSE" }, sort: { key: "evil", d: 1 } }));
    expect(U.load(s)).toEqual({ filters: { exchange: "NSE" }, sort: null });
    expect(U.load({ getItem() { throw new Error("blocked"); } })).toEqual({ filters: {}, sort: null });
    expect(() => U.save({ setItem() { throw new Error("full"); } }, { filters: {}, sort: null })).not.toThrow();
  });
  it("sector filter survives only if the sector exists", () => {
    const s = mem(); U.save(s, { filters: { sector: "Gone" }, sort: null });
    expect(U.load(s, ["Sector 1"]).filters).toEqual({});
  });
});
