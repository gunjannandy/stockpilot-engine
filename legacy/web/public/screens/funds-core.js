/* T26: the fund screen's rules (no look). Plain script (browser) that also loads in Node for tests.
   A series is { dates: ["YYYY-MM-DD"...], nav: [number...] }, oldest first, as in funds/{id}.json. */
(function (root) {
  "use strict";
  const DAY = 86400000, YEAR = 365.25 * DAY;
  const t = d => Date.parse(d);
  // Last index whose date is on or before time `at` (-1 when the series starts later).
  function at(s, when) {
    let lo = 0, hi = s.dates.length - 1, r = -1;
    while (lo <= hi) { const m = (lo + hi) >> 1; if (t(s.dates[m]) <= when) { r = m; lo = m + 1; } else hi = m - 1; }
    return r;
  }
  const ok = s => s && s.dates && s.dates.length > 1;
  // Yearly rate in percent between two moments, from the NAVs on or before each.
  function rate(s, from, to) {
    const a = at(s, from), b = at(s, to);
    if (a < 0 || b <= a || !(s.nav[a] > 0) || !(s.nav[b] > 0)) return null;
    if (t(s.dates[a]) < from - 10 * DAY) { /* old enough */ }
    const yrs = (t(s.dates[b]) - t(s.dates[a])) / YEAR;
    return yrs <= 0 ? null : (Math.pow(s.nav[b] / s.nav[a], 1 / yrs) - 1) * 100;
  }
  function cagr(s, years) {
    if (!ok(s)) return null;
    const end = t(s.dates[s.dates.length - 1]), from = end - years * YEAR;
    if (t(s.dates[0]) > from + 10 * DAY) return null;      // younger than the window
    return rate(s, from, end);
  }
  // Monthly points: the yearly rate of the `years` ending on each date.
  function rolling(s, years) {
    if (!ok(s)) return [];
    const first = t(s.dates[0]) + years * YEAR, last = t(s.dates[s.dates.length - 1]), out = [], step = 30.4375 * DAY;
    for (let when = first; when <= last + 1; when += step) {
      const i = at(s, when), r = rate(s, when - years * YEAR, when);
      if (r != null && i >= 0) out.push({ date: s.dates[i], ret: r });
    }
    return out;
  }
  function rollStats(r) {
    if (!r.length) return null;
    const v = r.map(x => x.ret).sort((a, b) => a - b), n = v.length;
    return { n, min: v[0], max: v[n - 1], median: n % 2 ? v[n >> 1] : (v[n / 2 - 1] + v[n / 2]) / 2, positive: v.filter(x => x > 0).length / n };
  }
  // Share of rolling-year windows in which the fund did better than another series (the Nifty).
  function beatShare(fund, other, years) {
    if (!ok(other)) return null;
    const pts = rolling(fund, years || 1); let n = 0, won = 0;
    for (const p of pts) {
      const when = t(p.date), o = rate(other, when - (years || 1) * YEAR, when);
      if (o == null || t(other.dates[0]) > when - (years || 1) * YEAR + 10 * DAY) continue;
      n++; if (p.ret > o) won++;
    }
    return n ? won / n : null;
  }
  // Against the middle fund of its kind: cat = { months: ["YYYY-MM"|date], med1y: [percent] } (funds/stats.json).
  function beatCategory(fund, cat) {
    if (!cat || !cat.months || !cat.months.length) return null;
    const m = new Map(cat.months.map((d, i) => [String(d).slice(0, 7), cat.med1y[i]]));
    let n = 0, won = 0;
    for (const p of rolling(fund, 1)) { const c = m.get(p.date.slice(0, 7)); if (c == null) continue; n++; if (p.ret > c) won++; }
    return n ? won / n : null;
  }
  // Bad markets, named in plain words by the screen. Dates are the Nifty's peak and trough of each fall.
  const MARKETS = [{ id: "gfc", from: "2008-01-08", to: "2009-03-09" }, { id: "covid", from: "2020-01-20", to: "2020-03-23" }, { id: "slide22", from: "2021-10-19", to: "2022-06-17" }];
  function deepest(s, from, to) {
    if (!ok(s)) return null;
    const a = at(s, t(from)), b = at(s, t(to)); if (b < 0) return null;
    const start = Math.max(a, 0);
    if (a < 0 && t(s.dates[0]) > t(from) + 20 * DAY) return null;     // launched after the fall began
    let peak = 0, worst = 0;
    for (let i = start; i <= b; i++) { const v = s.nav[i]; if (!(v > 0)) continue; if (v > peak) peak = v; worst = Math.min(worst, v / peak - 1); }
    return b - start < 1 ? null : worst * 100;
  }
  function falls(fund, bench) {
    const out = [];
    for (const m of MARKETS) {
      const f = deepest(fund, m.from, m.to); if (f == null) continue;
      out.push({ id: m.id, from: m.from, to: m.to, fund: f, bench: bench ? deepest(bench, m.from, m.to) : null });
    }
    return out;
  }
  function worstFall(s) {
    if (!ok(s)) return null;
    let peak = 0, worst = 0; for (const v of s.nav) { if (v > peak) peak = v; if (peak > 0) worst = Math.min(worst, v / peak - 1); }
    return worst * 100;
  }
  const RANGE_YEARS = { "1Y": 1, "3Y": 3, "5Y": 5, "10Y": 10 };
  function slice(s, range) {
    if (!ok(s) || !RANGE_YEARS[range]) return s;
    const from = t(s.dates[s.dates.length - 1]) - RANGE_YEARS[range] * YEAR;
    let i = at(s, from); if (i < 0) i = 0;
    return { dates: s.dates.slice(i), nav: s.nav.slice(i) };
  }
  // The owner's own buys (lots: acquired_on, quantity, cost) as dots on the chart.
  function buyDots(s, lots) {
    if (!ok(s)) return [];
    const lo = t(s.dates[0]), hi = t(s.dates[s.dates.length - 1]);
    return (lots || []).filter(l => l.acquired_on && t(l.acquired_on) >= lo && t(l.acquired_on) <= hi)
      .map(l => ({ i: at(s, t(l.acquired_on)), date: l.acquired_on, quantity: l.quantity, cost: l.cost }));
  }
  // Same rule as stockpilot.sources.fund_holdings.overlap: equities are INE ISINs.
  function overlap(rows, held) {
    if (!rows || !rows.length) return null;
    const H = new Set([...held].map(x => String(x).toUpperCase()));
    const shared = rows.filter(r => H.has(r.isin)).map(r => ({ isin: r.isin, name: r.name, pct_nav: r.pct_nav }));
    const eq = rows.filter(r => String(r.isin).startsWith("INE"));
    return { shared, n_shared: shared.length, n_held: H.size, pct_nav: Math.round(shared.reduce((a, s) => a + (s.pct_nav || 0), 0) * 100) / 100,
      pct_of_fund_stocks: eq.length ? Math.round(1000 * eq.filter(r => H.has(r.isin)).length / eq.length) / 10 : 0 };
  }
  // Fuzzy find over fund names, on the same engine as the stock search.
  function finder(Fuse, entries) {
    const eng = root.SPSearch.createSearch(Fuse, entries.map(e => ({ symbol: e.id, name: `${e.name} ${e.amc || ""}` })), { limit: 60 });
    const by = new Map(entries.map(e => [e.id, e]));
    return {
      find(q, f) {
        f = f || {};
        const base = String(q || "").trim() ? eng.find(q).map(x => by.get(x.symbol)) : entries;
        return base.filter(e => (!f.group || e.group === f.group) && (!f.amc || e.amc === f.amc));
      },
    };
  }
  function vs(a, b) { return a == null || b == null ? null : a - b > 1 ? "ahead" : a - b < -1 ? "behind" : "level"; }
  root.SPFundsCore = { cagr, rolling, rollStats, beatShare, beatCategory, falls, worstFall, slice, buyDots, overlap, finder, vs, MARKETS, RANGES: ["1Y", "3Y", "5Y", "10Y", "All"] };
})(typeof window !== "undefined" ? window : globalThis);
