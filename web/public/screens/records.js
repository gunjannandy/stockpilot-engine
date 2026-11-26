// T29: data and rules for Holdings, Tax, Trading record, Our record and RSUs on the live API.
// Behaviour only, no look: app.js draws what this returns. Plain script (browser) that also loads in Node for tests.
(function (root) {
  "use strict";
  const VIEWS = ["portfolio", "smallcase", "record", "own_record"];   // the names views_get serves (schemas/live-contract.json)
  const EPS = 1e-6;

  // The live API first. A view it has not been given yet (404) or cannot reach falls back to the last static file,
  // so the screen never goes blank during the move. A view found nowhere is null; the screen then says "no data".
  async function load(fetchFn, staticLoader) {
    const docs = {}, live = {};
    await Promise.all(VIEWS.map(async name => {
      try {
        const r = await fetchFn("/api/v2/views/" + name);
        if (!r.ok) throw new Error("HTTP " + r.status);
        const j = await r.json();
        if (!j || j.doc == null) throw new Error("empty");
        docs[name] = j.doc; live[name] = true;
      } catch (e) {
        live[name] = false;
        try { docs[name] = await staticLoader(name); } catch (e2) { docs[name] = null; }
      }
    }));
    return { docs, live };
  }

  // Units a holding came in through each route. A holding with no split counts as Kite.
  const split = h => {
    const s = h.by_source;
    return s && (s.kite != null || s.smallcase != null)
      ? { kite: +s.kite || 0, smallcase: +s.smallcase || 0 }
      : { kite: +h.quantity || 0, smallcase: 0 };
  };
  const sourceCounts = hs => ({ all: hs.length, kite: hs.filter(h => split(h).kite > EPS).length, smallcase: hs.filter(h => split(h).smallcase > EPS).length });

  // Rows for one route: its units, its share of the row's value and cost, the gain per unit unchanged, shares re-based on what is shown.
  function holdingsFor(hs, src) {
    if (!src || src === "all") return hs.map(h => ({ ...h }));
    const rows = [];
    for (const h of hs) {
      const units = split(h)[src];
      if (!(units > EPS)) continue;
      const f = h.quantity ? units / h.quantity : 0;
      rows.push({ ...h, quantity: units, value: Math.round((h.value || 0) * f), lots_units: null, check: null });
    }
    const total = rows.reduce((a, h) => a + h.value, 0);
    rows.forEach(h => { h.share = total ? h.value / total : 0; });
    return rows;
  }

  // The line under the table. It is the sum of the rows on screen, so a number can never disagree with the rows.
  function summary(rows) {
    const value = rows.reduce((a, h) => a + (h.value || 0), 0), cost = rows.reduce((a, h) => a + (h.avg_cost || 0) * (h.quantity || 0), 0);
    return { count: rows.length, value, cost, gain: value - cost, gain_pct: cost ? (value - cost) / cost : 0 };
  }

  // Units check: Kite's units for a holding against the units our own lots explain.
  function unitsCheck(hs) {
    const withLots = hs.filter(h => h.lots_units != null);
    return {
      checked: withLots.length,
      off: withLots.filter(h => Math.abs(h.quantity - h.lots_units) > EPS).map(h => ({ symbol: h.symbol, name: h.name, held: h.quantity, lots: h.lots_units, diff: Math.round((h.quantity - h.lots_units) * 1e6) / 1e6 })),
      noted: hs.filter(h => h.check).map(h => ({ symbol: h.symbol, name: h.name, note: h.check })),
    };
  }

  root.SPRecords = { VIEWS, load, split, sourceCounts, holdingsFor, summary, unitsCheck };
})(typeof window !== "undefined" ? window : globalThis);
