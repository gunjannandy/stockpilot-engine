// T24: the Worth following screen. One list for every candidate that is not held:
// "No forecast yet" with Analyse where no model view exists, snooze and cross as in v10.
// Pure functions plus a small controller; app.js hands in the page's helpers and hooks the screen in with a few lines.
(function (root) {
  "use strict";
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // Fixed screen words. app.js merges these into its one word table; the build gate (T30) checks every one has Bengali.
  const WORDS = {
    en: {
      wfLead: "Stocks worth a look that you do not own. No forecast yet? Press Analyse.",
      wfNoFc: "No forecast yet", wfAnalyse: "Analyse", wfRunning: "Analysing", wfOod: "Out of date",
      wfStrong: "Strong", wfFair: "Fair", wfWeak: "Weak", wfChance: "chance",
      wfEmpty: "Nothing to follow right now.", wfLoading: "Loading the list...", wfFailed: "Could not load this list. Check your connection and try again.", wfRetry: "Try again",
      wfAnalyseStarted: "Started. The forecast will appear here.", wfTipStrong: "Out of 100 times, this many stocks like it beat the Nifty. 57 or more is strong.", wfTipWeak: "Below 40 is weak.",
    },
    bn: {
      wfLead: "আপনার নেই, অথচ দেখার মতো stock। Forecast নেই? Analyse চাপুন।",
      wfNoFc: "এখনও forecast নেই", wfAnalyse: "Analyse", wfRunning: "দেখা হচ্ছে", wfOod: "পুরনো হয়ে গেছে",
      wfStrong: "Strong", wfFair: "Fair", wfWeak: "Weak", wfChance: "সম্ভাবনা",
      wfEmpty: "এখন নজরে রাখার মতো কিছু নেই।", wfLoading: "তালিকা আসছে...", wfFailed: "তালিকাটা আনা গেল না। Internet দেখে আবার চেষ্টা করুন।", wfRetry: "আবার চেষ্টা করুন",
      wfAnalyseStarted: "শুরু হয়েছে। forecast এখানেই দেখাবে।", wfTipStrong: "এরকম 100টা stock-এর মধ্যে এতগুলো Nifty-কে ছাড়িয়েছে। 57 বা বেশি মানে strong।", wfTipWeak: "40-এর নিচে মানে weak।",
    },
  };
  const word = (lang, k) => (WORDS[lang] && WORDS[lang][k]) ?? WORDS.en[k];

  const key = i => i.symbol + ":" + (i.exchange || "NSE");
  // Held stocks never show (by symbol, whatever the exchange); hidden ones (snoozed or crossed) drop out at once.
  function rowsOf(items, { held, hidden }) {
    return (items || []).filter(i => !held.has(i.symbol) && !hidden.has(i.symbol)).slice().sort((a, b) => (a.rank || 0) - (b.rank || 0));
  }
  const meterOf = p => p >= 0.57 ? "strong" : p < 0.40 ? "weak" : "fair";
  const VERDICT = { buy: "buy", hold: "hold", sell: "sell", wait: "watch" };

  function progressHtml(job, lang) {
    const L = root.SPLive;
    if (L && L.jobProgressHtml) return L.jobProgressHtml(job, lang);
    return "";
  }

  // opt: { name(sym), lang, w(key, ...args) optional, job optional {job, lines}, star(sym) optional html, chipHtml(verdict) optional }
  function rowHtml(i, opt) {
    const lang = opt.lang || "en", t = k => opt.w ? opt.w(k) : word(lang, k);
    const sym = esc(i.symbol), nm = esc(opt.name ? opt.name(i.symbol) : i.symbol);
    const why = lang === "bn" && i.reason_bn ? i.reason_bn : i.reason;
    const has = !!i.call, v = has ? VERDICT[i.call] || "watch" : "none";
    const running = opt.job && opt.job.job && (opt.job.job.status === "queued" || opt.job.job.status === "running");
    const chipTxt = opt.chipHtml ? opt.chipHtml(v) : `<span class="chip v-${v}">${esc(v)}</span>`;
    let right;
    if (has) {
      const m = i.chance_3m == null ? null : meterOf(i.chance_3m);
      right = `${i.chance_3m == null ? "" : `<b class="num wf-p">${Math.round(i.chance_3m * 100)}%</b><span class="wf-meter wf-${m}" data-tip="${esc(t(m === "weak" ? "wfTipWeak" : "wfTipStrong"))}">${esc(t("wf" + m[0].toUpperCase() + m.slice(1)))}</span>`}${i.out_of_date ? `<span class="wf-ood">${esc(t("wfOod"))}</span>` : ""}`;
    } else if (running) right = `<span class="wf-run"><span class="ms">sync</span>${esc(t("wfRunning"))}</span>`;
    else right = `<button type="button" class="btn f sm wf-an" data-analyse="${sym}" data-ex="${esc(i.exchange || "NSE")}"><span class="ms">query_stats</span>${esc(t("wfAnalyse"))}</button>`;
    const sub = has ? esc(why) : `<b>${esc(t("wfNoFc"))}</b>`;
    const prog = opt.job && opt.job.job && !has ? `<div class="wf-prog">${progressHtml(opt.job, lang)}</div>` : "";
    const dot = opt.dot ? opt.dot(i.symbol) : "";
    return `<div class="lrow wf-row r-${v}" role="option" data-sel="${esc(opt.key || "follow")}:${sym}" aria-selected="${opt.selected === i.symbol}" tabindex="0" data-sym="${sym}">
  ${chipTxt}<span class="lm"><b class="trunc">${nm}${dot}</b><span class="ls trunc">${sub}</span></span>
  <span class="lspc">${opt.spark ? opt.spark(i.symbol) : ""}</span><span class="lr wf-r">${right}</span>
  <span class="cx wf-x"><button type="button" class="icb" data-snooze="${sym}" data-tip="${esc(opt.w ? opt.w("snoozeShort") : "Hide for 30 days")}" aria-label="${esc(opt.w ? opt.w("snoozeShort") : "Hide for 30 days")}"><span class="ms">schedule</span></button><button type="button" class="icb" data-dismiss="${sym}" data-tip="${esc(opt.w ? opt.w("cross") : "Never show this again")}" aria-label="${esc(opt.w ? opt.w("cross") : "Never show this again")}"><span class="ms">block</span></button></span>${opt.star ? opt.star(i.symbol) : ""}${prog}</div>`;
  }

  // The right-hand pane for a stock the page holds no v10 view of: what the list knows, and Analyse where there is no call.
  function paneHtml(i, opt) {
    const lang = opt.lang || "en", t = k => opt.w ? opt.w(k) : word(lang, k), sym = esc(i.symbol);
    const has = !!i.call, v = has ? VERDICT[i.call] || "watch" : "none", why = lang === "bn" && i.reason_bn ? i.reason_bn : i.reason;
    const chipTxt = opt.chipHtml ? opt.chipHtml(v) : `<span class="chip v-${v}">${esc(v)}</span>`;
    const m = has && i.chance_3m != null ? meterOf(i.chance_3m) : null;
    const body = has
      ? `<div class="pn-view"><p class="bigview">${esc(why)}</p>${m ? `<div class="pn-ch"><div><span class="bigp num">${Math.round(i.chance_3m * 100)}%</span><small class="muted cap">${esc(t("wfChance"))}</small></div><span class="wf-meter wf-${m}">${esc(t("wf" + m[0].toUpperCase() + m.slice(1)))}</span></div>` : ""}${i.out_of_date ? `<p class="wf-ood">${esc(t("wfOod"))}</p>` : ""}</div>`
      : `<div class="ask pn-ask"><div><h3>${esc(t("wfNoFc"))}</h3></div>${opt.running ? `<span class="wf-run"><span class="ms">sync</span>${esc(t("wfRunning"))}</span>` : `<button type="button" class="btn f" data-analyse="${sym}" data-ex="${esc(i.exchange || "NSE")}"><span class="ms">query_stats</span>${esc(t("wfAnalyse"))}</button>`}</div>`;
    return `<div class="pn-top"><div style="min-width:0"><div class="sb-chips">${chipTxt}</div><h2 class="trunc">${esc(opt.name ? opt.name(i.symbol) : i.symbol)}</h2><div class="muted num">${sym}</div></div><div class="pn-r"><div class="pn-btns">${opt.star ? opt.star(i.symbol) : ""}</div></div></div>${body}`;
  }

  // The controller holds the list, the hidden set and the running Analyse jobs; the page re-renders through rerender().
  function createController(o) {
    let items = [], loaded = false, loading = false, failed = false;
    const hidden = new Set(), jobs = new Map(), byJob = new Map();
    const j = async (url, init) => { const r = await o.fetch(url, init); if (!r || !r.ok) throw new Error("HTTP " + (r && r.status)); return r.json(); };
    const self = {
      rows: () => rowsOf(items, { held: o.held(), hidden }),
      loaded: () => loaded, loading: () => loading, error: () => failed,
      jobOf: sym => jobs.get(sym) || null,
      itemOf: sym => items.find(i => i.symbol === sym) || null,
      async load() {
        if (loading) return; loading = true;
        try { const r = await j("/api/v2/lists/worth_following"); items = r.items || []; failed = false; loaded = true; }
        catch (e) { failed = true; loaded = true; }
        loading = false; o.rerender && o.rerender();
      },
      async snooze(sym) { hidden.add(sym); o.rerender && o.rerender(); return o.queue("snooze", { symbol: sym, scope: "stock" }, o.say ? o.say("snoozed") : "Hidden", () => { hidden.delete(sym); o.rerender && o.rerender(); }); },
      async dismiss(sym) { hidden.add(sym); o.rerender && o.rerender(); return o.queue("dismiss", { symbol: sym, scope: "stock" }, o.say ? o.say("dismissed") : "Hidden", () => { hidden.delete(sym); o.rerender && o.rerender(); }); },
      async analyse(sym) {
        if (jobs.has(sym)) return;
        const it = items.find(i => i.symbol === sym), ex = (it && it.exchange) || "NSE";
        jobs.set(sym, { job: { id: null, status: "queued", kind: "analyse" }, lines: [] }); o.rerender && o.rerender();
        try {
          const r = await j("/api/v2/jobs", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ kind: "analyse", payload: { symbol: sym, exchange: ex } }) });
          byJob.set(r.id, sym); jobs.get(sym).job.id = r.id; o.watchJob(r.id);
        } catch (e) {
          jobs.delete(sym); o.rerender && o.rerender(); o.say && o.toast && o.toast(o.say("fail"));
        }
      },
      async onJob(e) {
        const sym = byJob.get(e.id); if (!sym || e.type !== "job") return;
        jobs.set(sym, { job: e.job, lines: e.lines || [] });
        if (e.job.status === "done") { jobs.delete(sym); byJob.delete(e.id); await self.reloadQuiet(); }
        else if (e.job.status === "failed") { o.rerender && o.rerender(); }
        else o.rerender && o.rerender();
      },
      async reloadQuiet() { try { const r = await j("/api/v2/lists/worth_following"); items = r.items || []; failed = false; } catch (e) { /* keep the old list */ } o.rerender && o.rerender(); },
      retry(sym) { jobs.delete(sym); return self.analyse(sym); },
    };
    return self;
  }

  root.SPWorth = { WORDS, rowsOf, rowHtml, paneHtml, meterOf, createController, esc, key };
  if (typeof module !== "undefined") module.exports = root.SPWorth;
})(typeof window !== "undefined" ? window : globalThis);
