/* T25: rules of the universe table (the screener): filters, sort, remembered choices. No look here.
   Works on the columns file screen/universe.json: arrays of equal length, null where we hold no figure. */
(function (root, factory) { root.SPUniverseCore = factory(); })(globalThis, function () {
  "use strict";
  const KEY = "sp.universe.v1";
  const num = v => v != null && Number.isFinite(v);
  // One choice per filter. "any" is the absence of a choice. A row with no figure never matches a range.
  const FILTERS = {
    pe:       { opts: { lt15: t => num(t.pe) && t.pe < 15, mid: t => num(t.pe) && t.pe >= 15 && t.pe <= 30, gt30: t => num(t.pe) && t.pe > 30, none: t => !num(t.pe) } },
    growth:   { opts: { up: t => num(t.growth) && t.growth > 15, slow: t => num(t.growth) && t.growth >= 0 && t.growth <= 15, down: t => num(t.growth) && t.growth < 0 } },
    chance:   { opts: { p60: t => num(t.chance_6m) && t.chance_6m >= 0.6, p50: t => num(t.chance_6m) && t.chance_6m >= 0.5 && t.chance_6m < 0.6, low: t => num(t.chance_6m) && t.chance_6m < 0.5, none: t => !num(t.chance_6m) } },
    size:     { opts: { large: t => num(t.mcap_cr) && t.mcap_cr >= 20000, mid: t => num(t.mcap_cr) && t.mcap_cr >= 5000 && t.mcap_cr < 20000, small: t => num(t.mcap_cr) && t.mcap_cr >= 500 && t.mcap_cr < 5000, tiny: t => num(t.mcap_cr) && t.mcap_cr < 500 } },
    exchange: { opts: { NSE: (t, i) => t.exchange[i] === "NSE", BSE: (t, i) => t.exchange[i] === "BSE", SME: (t, i) => /SME/.test(t.segment[i]) } },
    sector:   { free: true },   // any sector that exists in the data
  };
  // The numeric ones read a single row; build a tiny view so the predicates above stay readable.
  const COLS = ["pe", "growth", "chance_6m", "mcap_cr"];
  const SORTABLE = ["name", "pe", "growth", "chance_6m", "mcap_cr", "last", "day_change_pct", "sector"];

  function matcher(t, filters) {
    const view = {}, tests = [];
    for (const [k, v] of Object.entries(filters || {})) {
      const f = FILTERS[k]; if (!f || v == null) continue;
      if (f.free) tests.push(i => t.sector[i] === v);
      else if (f.opts[v]) { const fn = f.opts[v]; tests.push(k === "exchange" ? (i => fn(t, i)) : (i => { for (const c of COLS) view[c] = t[c][i]; return fn(view, i); })); }
    }
    return i => { for (const f of tests) if (!f(i)) return false; return true; };
  }
  const norm = s => String(s || "").toLowerCase();
  // -> array of row numbers, filtered, matched on the typed words (each must appear in name or symbol), sorted.
  function run(t, filters, sort, query) {
    const ok = matcher(t, filters), words = norm(query).split(/\s+/).filter(Boolean), out = [];
    for (let i = 0; i < t.n; i++) {
      if (!ok(i)) continue;
      if (words.length) { const hay = norm(t.name[i]) + " " + norm(t.symbol[i]); if (!words.every(w => hay.includes(w))) continue; }
      out.push(i);
    }
    if (sort && SORTABLE.includes(sort.key)) {
      const col = t[sort.key], d = sort.d < 0 ? -1 : 1, text = sort.key === "name" || sort.key === "sector";
      out.sort((a, b) => {
        const x = col[a], y = col[b], nx = x == null, ny = y == null;
        if (nx || ny) return nx === ny ? a - b : nx ? 1 : -1;     // missing figures last, either direction
        const c = text ? String(x).localeCompare(String(y)) : x - y;
        return c ? d * c : a - b;
      });
    }
    return out;
  }
  function sectors(t) {
    const n = new Map(); for (const s of t.sector) if (s) n.set(s, (n.get(s) || 0) + 1);
    return [...n].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(x => x[0]);
  }
  // How many rows each choice would leave, for the number on a chip (other filters held as they are).
  function counts(t, filters, query, key) {
    const f = FILTERS[key], out = {}; if (!f || f.free) return out;
    for (const o of Object.keys(f.opts)) out[o] = run(t, { ...filters, [key]: o }, null, query).length;
    return out;
  }
  function save(storage, st) { try { storage.setItem(KEY, JSON.stringify({ filters: st.filters || {}, sort: st.sort || null })); } catch (e) { /* storage may be blocked */ } }
  function load(storage, knownSectors) {
    const empty = { filters: {}, sort: null };
    try {
      const raw = JSON.parse(storage.getItem(KEY) || "null"); if (!raw || typeof raw !== "object") return empty;
      const filters = {};
      for (const [k, v] of Object.entries(raw.filters || {})) {
        const f = FILTERS[k]; if (!f) continue;
        if (f.free ? (knownSectors ? knownSectors.includes(v) : typeof v === "string") : Object.prototype.hasOwnProperty.call(f.opts, v)) filters[k] = v;
      }
      const s = raw.sort, sort = s && SORTABLE.includes(s.key) && (s.d === 1 || s.d === -1) ? { key: s.key, d: s.d } : null;
      return { filters, sort };
    } catch (e) { return empty; }
  }
  return { KEY, FILTERS, SORTABLE, run, sectors, counts, save, load };
});
