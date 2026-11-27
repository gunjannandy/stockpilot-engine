/* T26: Mutual funds. Every fund is searchable and opens as a page as detailed as a stock page: NAV chart since launch with
   the owner's buys, returns against the middle fund of its kind and the Nifty, rolling returns, falls in bad markets,
   consistency, cost and size, overlap with held stocks, our forecast, a watch star.
   Data (public files, loaded once): funds/index.json, funds/stats.json, funds/{id}.json, fund_holdings/{id}.json.
   All words come in through ctx.w (the one word table in app.js). Pure rules are in funds-core.js. */
(function (root) {
  "use strict";
  const C = root.SPFundsCore, PAGE = 50;
  const cache = new Map();
  const getJSON = u => { if (!cache.has(u)) cache.set(u, fetch(u).then(r => r.ok ? r.json() : null).catch(() => null)); return cache.get(u); };
  let ctx = null, box = null, index = null, stats = null, finder = null, st = { q: "", group: "", amc: "", sort: "rel", shown: PAGE }, wired = false, view = null;

  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const f1 = v => v == null ? "–" : (v > 0 ? "+" : "") + v.toFixed(1) + "%";
  const tone = v => v == null ? "" : v >= 0 ? "up" : "dn";
  const cr = v => v == null ? "–" : v >= 100000 ? (v / 100000).toFixed(1) + " L cr" : Math.round(v).toLocaleString("en-IN") + " cr";
  const when = d => { const x = new Date(d + "T00:00"); return isNaN(x) ? d : x.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }); };
  const costOf = e => e.ter_direct != null ? e.ter_direct : e.ter_regular;
  const SMALL_CR = 500;

  function prepare(idx, stt) {
    index = idx.entries;
    const col = stt && stt.funds && stt.funds.id ? stt.funds : null, byId = new Map();
    if (col) col.id.forEach((id, i) => byId.set(id, { r1: col.r1[i], r3: col.r3[i], r5: col.r5[i] }));
    const cats = new Map(((stt && stt.categories) || []).map(c => [c.name, c]));
    stats = { byId, cats };
    finder = C.finder(root.Fuse, index);
  }
  const load = () => Promise.all([getJSON("funds/index.json"), getJSON("funds/stats.json")]).then(([i, s]) => { if (i && Array.isArray(i.entries)) prepare(i, s); return !!index; });

  // ---- list ----
  const groups = () => [...new Set(index.map(e => e.group).filter(Boolean))].sort();
  const houses = () => [...new Set(index.map(e => e.amc).filter(Boolean))].sort();
  const SORTS = { rel: null, r3: e => -(stats.byId.get(e.id)?.r3 ?? -999), cost: e => costOf(e) ?? 99, size: e => -(e.aum_cr ?? -1), name: e => e.name };
  function results() {
    const out = finder.find(st.q, { group: st.group, amc: st.amc }), k = SORTS[st.sort];
    return k ? out.slice().sort((a, b) => { const x = k(a), y = k(b); return typeof x === "string" ? x.localeCompare(y) : x - y; }) : out;
  }
  const vsChip = (e, s) => {
    const c = stats.cats.get(e.category), v = c && s && s.r3 != null && c.r3 != null ? C.vs(s.r3, c.r3) : null;
    return v ? `<span class="fxv fxv-${v}">${ctx.w("fxVs_" + v)}</span>` : "";
  };
  function listBody() {
    const w = ctx.w, rows = results();
    const tr = e => { const s = stats.byId.get(e.id) || {};
      return `<tr class="r" data-fx="${esc(e.id)}" tabindex="0"><td class="nm"><b>${esc(e.name)}</b><div class="sy muted">${esc((e.amc || "").replace(/ Mutual Fund$/, ""))} · ${esc(e.group || e.category || "")}${e.variants > 1 ? ` · ${w("fxVariants", e.variants)}` : ""}</div></td>
        <td class="r num h1 ${tone(s.r1)}">${f1(s.r1)}</td><td class="r num ${tone(s.r3)}">${f1(s.r3)}</td><td class="h1">${vsChip(e, s)}</td>
        <td class="r num h2">${costOf(e) != null ? costOf(e).toFixed(2) + "%" : "–"}</td><td class="r num h2">${cr(e.aum_cr)}</td></tr>`; };
    const list = rows.slice(0, st.shown);
    return `<p class="uct" role="status"><b class="num">${rows.length.toLocaleString("en-IN")}</b> ${w("fxOf")} <span class="num">${index.length.toLocaleString("en-IN")}</span> ${w("fxFunds")}</p>
      ${rows.length ? `<table class="grid fxg"><thead><tr><th><button tabindex="-1">${w("fxColFund")}</button></th><th class="r h1"><button tabindex="-1">${w("fxCol1y")}</button></th><th class="r"><button tabindex="-1">${w("fxCol3y")}</button></th><th class="h1"><button tabindex="-1">${w("fxColVs")}</button></th><th class="r h2"><button tabindex="-1">${w("fxColCost")}</button></th><th class="r h2"><button tabindex="-1">${w("fxColSize")}</button></th></tr></thead><tbody>${list.map(tr).join("")}</tbody></table>
      ${rows.length > st.shown ? `<p class="umore"><button class="btn t" data-fxmore>${w("uMore", Math.min(PAGE, rows.length - st.shown))}</button></p>` : ""}` : `<p class="muted" style="padding:24px 4px">${w("fxNone")}</p>`}`;
  }
  const opt = (v, cur, label) => `<option value="${esc(v)}"${v === cur ? " selected" : ""}>${esc(label)}</option>`;
  function paintList() {
    const w = ctx.w; box.innerHTML = `<header class="lead"><div class="lead-t"><h1>${w("funds")}</h1><p>${w("fxP")}</p></div></header>
      <div class="tools"><label class="qf"><span class="ms" style="font-size:18px">search</span><input id="fxq" value="${esc(st.q)}" placeholder="${esc(w("fxFind"))}" autocomplete="off" aria-label="${esc(w("fxFind"))}"></label></div>
      <div class="fxfil"><label>${w("fxKind")} <select id="fxg">${opt("", st.group, w("uAny"))}${groups().map(g => opt(g, st.group, g)).join("")}</select></label>
      <label>${w("fxHouse")} <select id="fxh">${opt("", st.amc, w("uAny"))}${houses().map(g => opt(g, st.amc, g.replace(/ Mutual Fund$/, ""))).join("")}</select></label>
      <label>${w("fxSort")} <select id="fxs">${["rel", "r3", "cost", "size", "name"].map(k => opt(k, st.sort, w("fxSort_" + k))).join("")}</select></label></div><div id="fxbody">${listBody()}</div>`;
  }

  // ---- chart ----
  function chartSvg(s, dots, wd, ht, bench) {
    const n = s.dates.length, lo0 = Math.min(...s.nav), hi0 = Math.max(...s.nav), pad = (hi0 - lo0) * .06 || 1, lo = lo0 - pad, hi = hi0 + pad;
    const L = 52, R = 8, T = 8, B = 22, X = i => L + (n < 2 ? 0 : i / (n - 1)) * (wd - L - R), Y = v => T + (1 - (v - lo) / (hi - lo)) * (ht - T - B);
    const step = Math.max(1, Math.floor(n / 600)), pts = []; for (let i = 0; i < n; i += step) pts.push(`${X(i).toFixed(1)},${Y(s.nav[i]).toFixed(1)}`); pts.push(`${X(n - 1).toFixed(1)},${Y(s.nav[n - 1]).toFixed(1)}`);
    const yt = [0, .25, .5, .75, 1].map(f => lo + (hi - lo) * f), yrs = [], seen = new Set();
    s.dates.forEach((d, i) => { const y = d.slice(0, 4); if (!seen.has(y)) { seen.add(y); yrs.push([i, y]); } });
    const every = Math.ceil(yrs.length / Math.max(2, Math.floor((wd - L) / 60))), xl = yrs.filter((_, k) => k % every === 0 && X(yrs[k][0]) > L + 12);
    return `<svg viewBox="0 0 ${wd} ${ht}" width="100%" height="${ht}" role="img" aria-label="${esc(ctx.w("fxChartAria"))}" class="fxsvg">
      ${yt.map(v => `<line x1="${L}" x2="${wd - R}" y1="${Y(v).toFixed(1)}" y2="${Y(v).toFixed(1)}" class="fxgrid"/><text x="${L - 6}" y="${(Y(v) + 4).toFixed(1)}" text-anchor="end" class="fxax">${v < 100 ? v.toFixed(1) : Math.round(v)}</text>`).join("")}
      ${xl.map(([i, y]) => `<text x="${X(i).toFixed(1)}" y="${ht - 6}" text-anchor="middle" class="fxax">${y}</text>`).join("")}
      <polygon points="${L},${ht - B} ${pts.join(" ")} ${X(n - 1).toFixed(1)},${ht - B}" class="fxarea"/><polyline points="${pts.join(" ")}" class="fxline"/>
      ${dots.map(d => `<circle cx="${X(d.i).toFixed(1)}" cy="${Y(s.nav[d.i]).toFixed(1)}" r="5" class="fxbuy"><title>${esc(ctx.w("fxBuyTip", when(d.date), d.quantity))}</title></circle>`).join("")}
      <line class="fxcur" x1="0" x2="0" y1="${T}" y2="${ht - B}" style="display:none"/></svg>`;
  }
  function drawChart(host, fund, lots, range) {
    const s = C.slice(fund, range), wd = Math.max(300, host.clientWidth || 700), ht = wd < 520 ? 230 : 320, dots = C.buyDots(s, lots);
    host.querySelector(".fxplot").innerHTML = chartSvg(s, dots, wd, ht);
    const svg = host.querySelector("svg"), cur = svg.querySelector(".fxcur"), out = host.querySelector(".fxread"), L = 52, R = 8;
    const at = ev => { const r = svg.getBoundingClientRect(), x = (ev.clientX - r.left) / r.width * wd, i = Math.max(0, Math.min(s.dates.length - 1, Math.round((x - L) / (wd - L - R) * (s.dates.length - 1))));
      cur.style.display = ""; const cx = L + i / (s.dates.length - 1) * (wd - L - R); cur.setAttribute("x1", cx); cur.setAttribute("x2", cx);
      out.innerHTML = `<b class="num">${when(s.dates[i])}</b> · ${ctx.w("fxNav")} <b class="num">${s.nav[i].toFixed(2)}</b>`; };
    svg.addEventListener("pointermove", at); svg.addEventListener("pointerleave", () => { cur.style.display = "none"; out.innerHTML = ""; });
    host.dataset.w = wd;
  }

  // ---- fund page ----
  const sec = (icon, h, p, body) => `<section class="fxsec"><h3><span class="ms" aria-hidden="true">${icon}</span>${h}</h3>${p ? `<p class="muted fxp">${p}</p>` : ""}${body}</section>`;
  const kv = (k, v, cls = "") => v == null || v === "" ? "" : `<div class="fkv"><span>${k}</span><b class="num ${cls}">${v}</b></div>`;

  function returnsTable(fund, e, bench) {
    const w = ctx.w, c = stats.cats.get(e.category), rows = [["fxR1", 1, "r1"], ["fxR3", 3, "r3"], ["fxR5", 5, "r5"], ["fxR10", 10, null]];
    const body = rows.map(([lab, y, k]) => { const a = C.cagr(fund, y), cat = k && c ? c[k] : null, b = bench ? C.cagr(bench, y) : null; if (a == null) return "";
      const v = C.vs(a, b != null ? b : cat), word = v ? w("fxVs_" + v) : "";
      return `<tr><td>${w(lab)}</td><td class="r num ${tone(a)}"><b>${f1(a)}</b></td><td class="r num">${f1(cat)}</td><td class="r num">${f1(b)}</td><td class="h1">${word ? `<span class="fxv fxv-${v}">${word}</span>` : ""}</td></tr>`; }).join("");
    return body ? `<table class="grid fxr"><thead><tr><th></th><th class="r"><button tabindex="-1">${w("fxThisFund")}</button></th><th class="r"><button tabindex="-1">${w("fxKindMid")}</button></th><th class="r"><button tabindex="-1">${w("fxNifty")}</button></th><th class="h1"></th></tr></thead><tbody>${body}</tbody></table>` : `<p class="muted">${w("fxTooYoung")}</p>`;
  }
  function rollingBlock(fund, bench) {
    const w = ctx.w, r = C.rollStats(C.rolling(fund, 3)); if (!r) return `<p class="muted">${w("fxTooYoung")}</p>`;
    const nb = bench ? C.rollStats(C.rolling(bench, 3)) : null;
    return `<div class="fgrid">${kv(w("fxRollWorst"), f1(r.min), tone(r.min))}${kv(w("fxRollMid"), f1(r.median), tone(r.median))}${kv(w("fxRollBest"), f1(r.max), tone(r.max))}${kv(w("fxRollLoss"), Math.round((1 - r.positive) * 100) + "%")}</div>
      <p class="muted fxp">${w("fxRollLine", r.n)} ${nb ? w("fxRollNifty", f1(nb.min), f1(nb.max)) : ""}</p>`;
  }
  function fallsBlock(fund, bench) {
    const w = ctx.w, fs = C.falls(fund, bench); if (!fs.length) return `<p class="muted">${w("fxNoFalls")}</p>`;
    return `<table class="grid fxr"><thead><tr><th></th><th class="r"><button tabindex="-1">${w("fxThisFund")}</button></th><th class="r"><button tabindex="-1">${w("fxNifty")}</button></th><th class="h1"></th></tr></thead><tbody>${fs.map(f => { const v = f.bench == null ? null : f.fund > f.bench + 1 ? "less" : f.fund < f.bench - 1 ? "more" : "same";
      return `<tr><td>${w("fxM_" + f.id)}<div class="sy muted">${when(f.from)} – ${when(f.to)}</div></td><td class="r num dn"><b>${f1(f.fund)}</b></td><td class="r num dn">${f1(f.bench)}</td><td class="h1">${v ? `<span class="fxv fxv-${v === "less" ? "ahead" : v === "more" ? "behind" : "level"}">${w("fxFall_" + v)}</span>` : ""}</td></tr>`; }).join("")}</tbody></table>`;
  }
  const pctWord = v => v == null ? "–" : Math.round(v * 100) + "%";
  function costBlock(f, e) {
    const w = ctx.w, c = f.costs || {}, d = c.ter_direct, r = c.ter_regular, aum = c.aum_cr;
    const lakh = d != null && r != null ? Math.round((r - d) / 100 * 100000) : null;
    return `<div class="fgrid">${kv(w("fxTerDirect"), d != null ? d.toFixed(2) + "%" : null)}${kv(w("fxTerRegular"), r != null ? r.toFixed(2) + "%" : null)}${kv(w("fxAum"), aum != null ? cr(aum) : null)}</div>
      ${lakh != null && lakh > 0 ? `<p class="muted fxp">${w("fxLakh", lakh.toLocaleString("en-IN"))}</p>` : ""}${aum != null && aum < SMALL_CR ? `<p class="fxwarn"><span class="ms" aria-hidden="true">info</span>${w("fxSmall")}</p>` : ""}`;
  }
  function overlapBlock(o, held, hasHoldings) {
    const w = ctx.w;
    if (!hasHoldings) return `<p class="muted">${w("fxOvNone")}</p>`;
    if (!held) return `<p class="muted">${w("fxOvNoHold")}</p>`;
    if (!o.n_shared) return `<p>${w("fxOvZero")}</p>`;
    return `<p class="fxbig"><b class="num">${o.pct_nav.toFixed(1)}%</b> ${w("fxOvOf")}</p><ul class="fxov">${o.shared.sort((a, b) => b.pct_nav - a.pct_nav).slice(0, 12).map(s => `<li><span>${esc(s.name)}</span><b class="num">${s.pct_nav != null ? s.pct_nav.toFixed(1) + "%" : "–"}</b></li>`).join("")}</ul>`;
  }

  function forecastBlock(e, job) {
    const w = ctx.w, isin = e.isin;
    if (!isin) return `<p class="muted">${w("fxFcNone")}</p>`;
    const call = view && view.call;
    if (job) return `<div class="fxjob" role="status"><b>${w("fxAnalysing")}</b><ol>${(job.lines || []).map(l => `<li data-state="${esc(l.state)}">${esc(ctx.lang() === "bn" && l.text_bn ? l.text_bn : l.text)}</li>`).join("")}</ol></div>`;
    if (call) return `<p class="fxbig"><b>${esc(w("fxCall_" + call.call) || call.call)}</b>${call.chance_3m != null ? ` <span class="muted">${w("fxChance", Math.round(call.chance_3m * 100))}</span>` : ""}</p>${call.out_of_date ? `<p class="fxwarn">${w("fxFcOld")}</p>` : ""}`;
    return `<p class="muted">${w("fxNoFc")}</p><button class="btn f" data-fxask="${esc(isin)}"><span class="ms">query_stats</span>${w("fxAnalyse")}</button>`;
  }

  async function pollJob(id, e, el) {
    for (let k = 0; k < 120 && box && box.isConnected && view && view.e === e; k++) {
      await new Promise(r => setTimeout(r, 3000));
      const j = await fetch("/api/v2/jobs/" + encodeURIComponent(id)).then(r => r.ok ? r.json() : null).catch(() => null);
      if (!j) continue;
      view.job = { lines: j.lines || [], status: j.job.status }; paintForecast(e);
      if (j.job.status === "done" || j.job.status === "failed") {
        view.job = null;
        if (j.job.status === "done") view.call = await fetchCall(e); else view.failed = true;
        return paintForecast(e);
      }
    }
  }
  const fetchCall = e => e.isin ? fetch(`/api/v2/calls/${encodeURIComponent(e.isin)}?exchange=AMFI`).then(r => r.ok ? r.json() : null).then(j => j && j.call).catch(() => null) : Promise.resolve(null);
  function paintForecast(e) {
    const el = box && box.querySelector("#fxfc"); if (!el || !view || view.e !== e) return;
    el.innerHTML = forecastBlock(e, view.job) + (view.failed ? `<p class="fxwarn">${ctx.w("fxFailed")}</p>` : "");
  }

  async function paintFund(id) {
    const w = ctx.w, e = index.find(x => x.id === id);
    if (!e) { box.innerHTML = `<p class="muted" style="padding:24px 4px">${w("fxMissing")} <a href="#funds">${w("fxBack")}</a></p>`; return; }
    box.innerHTML = `<p class="muted" style="padding:24px 4px">${w("fxLoading")}</p>`;
    view = { e, call: null, job: null };
    const [f, bench, hold] = await Promise.all([getJSON(`funds/${encodeURIComponent(id)}.json`), ctx.bench(), getJSON(`fund_holdings/${encodeURIComponent(id)}.json`)]);
    if (!box || !box.isConnected || view.e !== e) return;
    if (!f) { box.innerHTML = `<p class="muted" style="padding:24px 4px">${w("fxMissing")} <a href="#funds">${w("fxBack")}</a></p>`; return; }
    const fund = f.nav && f.nav.dates && f.nav.dates.length > 1 ? f.nav : null, held = ctx.holding(e.isin), lots = (held && held.lots) || [];
    const o = hold ? C.overlap(hold.holdings, ctx.heldIsins()) : null, nh = ctx.heldIsins().size > 0;
    const latest = (f.variants || []).find(v => v.code === (f.nav && f.nav.code)) || (f.variants || [])[0] || {};
    const first = fund ? fund.dates[0] : null, c = stats.cats.get(e.category);
    const cons = fund ? { cat: C.beatCategory(fund, c), nifty: C.beatShare(fund, bench, 1) } : {};
    box.innerHTML = `<p class="fxback"><a href="#funds" class="btn t"><span class="ms">arrow_back</span>${w("fxBack")}</a></p>
      <header class="fxhead"><div style="min-width:0"><h1 class="fxh1">${esc(f.name)}</h1><div class="muted">${esc(f.amc || "")} · ${esc(e.group || f.category || "")}</div>
        <div class="fxvars">${(f.variants || []).map(v => `<span class="chip${v.code === (f.nav && f.nav.code) ? " v-hold" : " v-none"}" title="${esc(v.label)}">${esc(v.plan)} ${esc(v.option)}${v.nav != null ? ` <b class="num fxvn">${v.nav.toFixed(2)}</b>` : ""}</span>`).join("")}</div></div>
        <div class="fxpx"><div class="px num">${latest.nav != null ? latest.nav.toFixed(2) : "–"}</div><div class="muted">${w("fxNavOn", latest.nav_date ? when(latest.nav_date) : "–")}</div>${e.isin ? ctx.starBtn(e.isin) : ""}</div></header>
      ${held ? `<div class="pn-hold"><span class="tag">${w("fxYouHold")}</span><span class="num">${Math.round(held.quantity * 100) / 100} ${w("fxUnits")}</span><span class="num">${ctx.inr(held.value)}</span>${held.gain_pct != null ? `<b class="num ${held.gain_pct >= 0 ? "up" : "dn"}">${(held.gain_pct > 0 ? "+" : "") + (held.gain_pct * 100).toFixed(1)}%</b>` : ""}</div>` : ""}
      ${fund ? `<section class="fxsec fxchart" id="fxch"><div class="fxbar"><div class="fxranges" role="group" aria-label="${esc(w("fxRange"))}">${C.RANGES.map(r => `<button class="fchip" data-fxr="${r}" aria-pressed="${r === (st.range || "All")}">${r === "All" ? w("fxAll") : r}</button>`).join("")}</div><span class="fxread muted" aria-live="polite"></span></div><div class="fxplot"></div>
        <p class="muted fxp">${w("fxChartP", when(first))}${lots.length ? " " + w("fxBuysP") : ""}</p></section>` : `<p class="muted">${w("fxNoNav")}</p>`}
      ${sec("query_stats", w("fxFcT"), w("fxFcP"), `<div id="fxfc">${forecastBlock(e, null)}</div>`)}
      ${fund ? sec("trending_up", w("fxRetT"), w("fxRetP"), returnsTable(fund, e, bench)) : ""}
      ${fund ? sec("history", w("fxRollT"), w("fxRollP"), rollingBlock(fund, bench)) : ""}
      ${fund ? sec("trending_down", w("fxFallT"), w("fxFallP"), fallsBlock(fund, bench)) : ""}
      ${fund ? sec("fact_check", w("fxConsT"), w("fxConsP"), `<div class="fgrid">${kv(w("fxConsCat"), pctWord(cons.cat))}${kv(w("fxConsNifty"), pctWord(cons.nifty))}${kv(w("fxWorst"), f1(C.worstFall(fund)), "dn")}</div>`) : ""}
      ${sec("savings", w("fxCostT"), w("fxCostP"), costBlock(f, e))}
      ${sec("pie_chart", w("fxOvT"), w("fxOvP"), overlapBlock(o, nh, !!hold))}
      ${(f.not_available || []).length ? `<p class="muted fxp">${w("fxNA", f.not_available.join(", "))}</p>` : ""}`;
    st.range = st.range || "All";
    if (fund) { const host = box.querySelector("#fxch"); drawChart(host, fund, lots, st.range); view.draw = () => drawChart(host, fund, lots, st.range); view.host = host; view.fund = fund; view.lots = lots;
      if (root.ResizeObserver) { const ro = new ResizeObserver(() => { if (host.isConnected && Math.abs(host.clientWidth - host.dataset.w) > 16) view.draw(); }); ro.observe(host); } }
    view.call = await fetchCall(e); paintForecast(e);
    ctx.onFund && ctx.onFund(e);
  }

  function wire() {
    if (wired) return; wired = true;
    document.addEventListener("click", ev => {
      if (!box || !box.isConnected || !box.contains(ev.target)) return; const el = s => ev.target.closest(s); let x;
      if ((x = el("[data-fx]"))) { location.hash = "funds/" + x.dataset.fx; return; }
      if (el("[data-fxmore]")) { st.shown += PAGE; box.querySelector("#fxbody").innerHTML = listBody(); return; }
      if ((x = el("[data-fxr]")) && view && view.fund) { st.range = x.dataset.fxr; box.querySelectorAll("[data-fxr]").forEach(b => b.setAttribute("aria-pressed", String(b === x))); view.draw(); return; }
      if ((x = el("[data-fxask]")) && view) { x.disabled = true; const e = view.e;
        fetch("/api/v2/jobs", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ kind: "analyse", payload: { symbol: x.dataset.fxask, exchange: "AMFI" } }) })
          .then(r => r.ok ? r.json() : Promise.reject(r.status)).then(j => { view.job = { lines: [] }; view.failed = false; paintForecast(e); pollJob(j.id, e); })
          .catch(() => { view.failed = true; paintForecast(e); }); }
    });
    document.addEventListener("keydown", ev => { if (ev.key === "Enter" && box && box.isConnected && ev.target.matches("tr[data-fx]")) ev.target.click(); });
    document.addEventListener("input", ev => { if (box && box.isConnected && ev.target.id === "fxq") { st.q = ev.target.value; st.shown = PAGE; box.querySelector("#fxbody").innerHTML = listBody(); } });
    document.addEventListener("change", ev => { if (!box || !box.isConnected) return; const m = { fxg: "group", fxh: "amc", fxs: "sort" }[ev.target.id]; if (m) { st[m] = ev.target.value; st.shown = PAGE; box.querySelector("#fxbody").innerHTML = listBody(); } });
  }

  // Mount into the page shell app.js drew. c: { w, esc, inr, lang, bench, holding, heldIsins, starBtn, onFund }. `id` is the fund to open, or empty for the list.
  function mount(el, c, id) {
    box = el; ctx = c; view = null; wire();
    el.innerHTML = `<p class="muted" style="padding:24px 4px">${c.w("fxLoading")}</p>`;
    load().then(ok => {
      if (box !== el || !el.isConnected) return;
      if (!ok) { el.innerHTML = `<p class="muted" style="padding:24px 4px">${c.w("fxUnavailable")}</p>`; return; }
      if (id) paintFund(id); else { paintList(); }
    });
  }
  const loaded = () => load().then(ok => ok ? index : null);
  root.SPFundsScreen = { mount, load: loaded, entries: () => index };
})(window);
