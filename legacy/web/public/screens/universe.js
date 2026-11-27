/* T25: "Every stock": the screener table over the whole universe (NSE, BSE and SME), filter chips and sortable columns.
   Loads screen/universe.json once. All words come in through ctx.w (the one word table in app.js). */
(function (root) {
  "use strict";
  const C = root.SPUniverseCore, PAGE = 100;
  let table = null, loading = null, st = null, shown = PAGE, query = "", box = null, ctx = null, wired = false;

  const GROUPS = [["pe", "uPe"], ["growth", "uGrowth"], ["chance", "uChance"], ["size", "uSize"], ["exchange", "uExch"]];
  const OPT_KEY = { pe: { lt15: "uPeLt15", mid: "uPeMid", gt30: "uPeGt30", none: "uPeNone" }, growth: { up: "uGrUp", slow: "uGrSlow", down: "uGrDown" },
    chance: { p60: "uChP60", p50: "uChP50", low: "uChLow", none: "uChNone" }, size: { large: "uSzLarge", mid: "uSzMid", small: "uSzSmall", tiny: "uSzTiny" },
    exchange: { NSE: "uNSE", BSE: "uBSE", SME: "uSME" } };
  const COLS = [["name", "cStock", ""], ["chance_6m", "uChance", "r"], ["pe", "uPe", "r h1"], ["growth", "uGrowth", "r h1"], ["mcap_cr", "uSize", "r h2"], ["last", "cPrice", "r"], ["sector", "uSector", "h3"]];

  const load = () => loading || (loading = fetch("screen/universe.json").then(r => r.ok ? r.json() : null).catch(() => null)
    .then(t => (table = t && Array.isArray(t.symbol) ? { ...t, n: t.symbol.length } : null)));
  const cr = v => v == null ? "–" : v >= 100000 ? (v / 100000).toFixed(1) + " L cr" : Math.round(v).toLocaleString("en-IN") + " cr";
  const sizeWord = v => v == null ? "" : v >= 20000 ? ctx.w("uSzLarge") : v >= 5000 ? ctx.w("uSzMid") : v >= 500 ? ctx.w("uSzSmall") : ctx.w("uSzTiny");

  function chips() {
    const w = ctx.w, f = st.filters;
    return GROUPS.map(([k, label]) => {
      const n = C.counts(table, f, query, k);
      return `<div class="ufg" role="group" aria-label="${ctx.esc(w(label))}"><span class="ufl">${w(label)}</span>
        <button class="fchip" data-uf="${k}:" aria-pressed="${!f[k]}">${w("uAny")}</button>
        ${Object.keys(OPT_KEY[k]).map(o => `<button class="fchip" data-uf="${k}:${o}" aria-pressed="${f[k] === o}">${w(OPT_KEY[k][o])} <span class="num">${n[o]}</span></button>`).join("")}</div>`;
    }).join("") + `<div class="ufg"><span class="ufl">${w("uSector")}</span><select id="usec" class="fchip" aria-label="${ctx.esc(w("uSector"))}"><option value="">${w("uAny")}</option>${C.sectors(table).map(s => `<option value="${ctx.esc(s)}"${f.sector === s ? " selected" : ""}>${ctx.esc(s)}</option>`).join("")}</select></div>`;
  }
  function body() {
    const w = ctx.w, t = table, rows = C.run(t, st.filters, st.sort, query), active = Object.keys(st.filters).length || query;
    const so = k => st.sort && st.sort.key === k ? (st.sort.d > 0 ? "ascending" : "descending") : "none";
    const head = COLS.map(([k, l, c]) => `<th class="${c}" aria-sort="${so(k)}"><button data-us="${k}">${w(l)}<span class="ms i" aria-hidden="true">${so(k) === "ascending" ? "arrow_upward" : so(k) === "descending" ? "arrow_downward" : ""}</span></button></th>`).join("");
    const tr = i => { const ch = t.chance_6m[i], sc = /SME/.test(t.segment[i]);
      return `<tr class="r" data-open="${ctx.esc(t.symbol[i])}" tabindex="0"><td class="nm"><b>${ctx.esc(t.name[i])}</b><div class="sy muted num">${ctx.esc(t.symbol[i])} · ${t.exchange[i]}${sc ? " · SME" : ""}</div></td>
        <td class="r num">${ch == null ? `<span class="muted" title="${ctx.esc(w("uNoView"))}">–</span>` : `<b class="${ch >= .6 ? "up" : ch < .5 ? "dn" : ""}">${Math.round(ch * 100)}%</b>`}</td>
        <td class="r num h1">${t.pe[i] == null ? "–" : t.pe[i].toFixed(1)}</td><td class="r num h1">${t.growth[i] == null ? "–" : `<span class="${t.growth[i] >= 0 ? "up" : "dn"}">${t.growth[i] > 0 ? "+" : ""}${Math.round(t.growth[i])}%</span>`}</td>
        <td class="r num h2">${cr(t.mcap_cr[i])}<div class="sy muted">${sizeWord(t.mcap_cr[i])}</div></td><td class="r num">${ctx.px(t.last[i])}</td><td class="h3 muted">${ctx.esc(t.sector[i] || "–")}</td></tr>`; };
    const list = rows.slice(0, shown);
    return `<p class="uct" role="status"><b class="num">${rows.length.toLocaleString("en-IN")}</b> ${w("uOf")} <span class="num">${t.n.toLocaleString("en-IN")}</span> ${w("uStocks")}${active ? ` <button class="btn t" data-uclear>${w("uClear")}</button>` : ""}</p>
      ${rows.length ? `<table class="grid ug"><thead><tr>${head}</tr></thead><tbody>${list.map(tr).join("")}</tbody></table>
      ${rows.length > shown ? `<p class="umore"><button class="btn t" data-umore>${w("uMore", Math.min(PAGE, rows.length - shown))}</button></p>` : ""}` : `<p class="muted" style="padding:24px 4px">${w("uNone")}</p>`}`;
  }
  function paint() {
    box.querySelector("#utools").innerHTML = chips();
    box.querySelector("#ubody").innerHTML = body();
    const n = Object.keys(st.filters).length; box.querySelector("#ufn").textContent = n ? "(" + n + ")" : "";
    C.save(root.localStorage, st);
  }
  function change(fn) { fn(); shown = PAGE; paint(); }

  function wire() {
    if (wired) return; wired = true;
    document.addEventListener("click", e => {
      if (!box || !box.isConnected) return; const el = s => e.target.closest(s); if (!box.contains(e.target)) return; let x;
      if ((x = el("[data-uf]"))) { const [k, v] = x.dataset.uf.split(":"); return change(() => { if (v) st.filters[k] = v; else delete st.filters[k]; }); }
      if ((x = el("[data-us]"))) { const k = x.dataset.us, s = st.sort; return change(() => { st.sort = s && s.key === k ? (s.d > 0 ? { key: k, d: -1 } : null) : { key: k, d: k === "name" || k === "sector" ? 1 : -1 }; }); }
      if (el("[data-umore]")) { shown += PAGE; return paint(); }
      if (el("[data-uclear]")) { query = ""; const q = box.querySelector("#uq"); if (q) q.value = ""; return change(() => { st.filters = {}; }); }
    });
    document.addEventListener("change", e => { if (box && box.isConnected && e.target.id === "usec") change(() => { if (e.target.value) st.filters.sector = e.target.value; else delete st.filters.sector; }); });
    document.addEventListener("input", e => { if (box && box.isConnected && e.target.id === "uq") { query = e.target.value; shown = PAGE; box.querySelector("#utools").innerHTML = chips(); box.querySelector("#ubody").innerHTML = body(); } });
  }

  // Mount into the page shell app.js drew. ctx: { w, esc, px }.
  function mount(el, c) {
    box = el; ctx = c; query = ""; shown = PAGE; wire();
    const w = c.w;
    el.innerHTML = `<header class="lead"><div class="lead-t"><h1>${w("universe")}</h1><p class="clamp">${w("universeP")}</p></div></header><p class="muted" style="padding:24px 4px">${w("uLoading")}</p>`;
    load().then(t => {
      if (box !== el || !el.isConnected) return;
      if (!t) { el.querySelector("p.muted").textContent = w("uMissing"); return; }
      st = C.load(root.localStorage, C.sectors(t));
      el.innerHTML = `<header class="lead"><div class="lead-t"><h1>${w("universe")}</h1><p class="clamp">${w("universeP")}</p></div></header>
        <div class="tools uni-tools"><label class="qf"><span class="ms" style="font-size:18px">search</span><input id="uq" placeholder="${c.esc(w("uFind"))}" autocomplete="off"></label></div>
        <details id="ufd" class="ufd"${matchMedia("(max-width:600px)").matches ? "" : " open"}><summary><span class="ms" aria-hidden="true">tune</span> <b>${w("uFilters")}</b> <span class="num" id="ufn"></span></summary><div id="utools" class="uni-chips"></div></details><div id="ubody"></div>`;
      paint();
    });
  }
  root.SPUniverseScreen = { mount };
})(window);
