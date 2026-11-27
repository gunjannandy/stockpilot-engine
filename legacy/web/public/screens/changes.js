// AUDIT #19: the yellow notification. The father asked to be shown, in yellow, whenever a list is updated or a prediction changes.
// live.js already knows the rules (which change belongs to which tab, what is unseen); nothing started it. This file starts the
// changes feed, puts a yellow dot on each menu item that has unseen changes, and shows "What changed" at the top of Today with
// what changed, when, and a way to dismiss. Plain script: loads in the browser and in Node for tests.
(function (root) {
  "use strict";
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const words = {
    en: {
      chgT: "What changed", chgOne: "1 change since you last looked", chgMany: n => `${n} changes since you last looked`,
      chgSeen: "Got it", chgAllSeen: "Got it, clear all", chgMore: n => `and ${n} more`,
      chgCall: "Call changed", chgChance: "Chance moved", chgLevel: "Price level crossed", chgForecast: "New forecast", chgIn: "Added to a list", chgOut: "Left a list", chgAsk: "Feedback update",
      chgListFollow: "Worth following", chgListWatch: "Watchlist", chgListHold: "Holdings", chgListNews: "In today's news",
    },
    bn: {
      chgT: "যা বদলেছে", chgOne: "শেষবার দেখার পর ১টা বদল", chgMany: n => `শেষবার দেখার পর ${n}টা বদল`,
      chgSeen: "দেখেছি", chgAllSeen: "দেখেছি, সব সরান", chgMore: n => `আরও ${n}টা`,
      chgCall: "Call বদলেছে", chgChance: "সম্ভাবনা সরেছে", chgLevel: "দামের স্তর পেরিয়েছে", chgForecast: "নতুন forecast", chgIn: "তালিকায় যোগ হয়েছে", chgOut: "তালিকা থেকে বাদ গেছে", chgAsk: "Feedback-এর খবর",
      chgListFollow: "নজরে রাখার মতো", chgListWatch: "Watchlist", chgListHold: "Holdings", chgListNews: "আজকের খবরে",
    },
  };

  // Which menu item a change lights up. A list change names its list in old_value (left) or new_value (entered).
  const TAB_OF_KIND = { call_changed: ["today"], chance_moved: ["today"], level_crossed: ["today"], forecast_ready: ["today"], ask_status: ["feedback"] };
  const TAB_OF_LIST = { worth_following: "follow", watchlist: "watchlist", holdings: "portfolio", in_the_news: "market" };
  const LIST_WORD = { worth_following: "chgListFollow", watchlist: "chgListWatch", holdings: "chgListHold", in_the_news: "chgListNews" };
  const KIND_WORD = { call_changed: "chgCall", chance_moved: "chgChance", level_crossed: "chgLevel", forecast_ready: "chgForecast", list_entered: "chgIn", list_left: "chgOut", ask_status: "chgAsk" };

  const listOf = c => c.kind === "list_entered" ? c.new_value : c.kind === "list_left" ? c.old_value : null;
  function tabsOf(c) {
    if (c.kind === "list_entered" || c.kind === "list_left") { const t = TAB_OF_LIST[listOf(c)]; return t ? [t] : ["follow"]; }
    return TAB_OF_KIND[c.kind] || [];
  }
  const isUnseen = c => !c.seen_at && (TAB_OF_KIND[c.kind] || c.kind === "list_entered" || c.kind === "list_left");
  // { tab: count } of unseen changes.
  function dotsOf(items) {
    const o = {};
    (items || []).filter(isUnseen).forEach(c => tabsOf(c).forEach(t => { o[t] = (o[t] || 0) + 1; }));
    return o;
  }
  const idsForTab = (items, tab) => (items || []).filter(c => isUnseen(c) && tabsOf(c).includes(tab)).map(c => c.id);

  function fmtAt(at) {
    const d = new Date(at); if (isNaN(d)) return "";
    const p = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false }).formatToParts(d);
    const g = k => p.find(x => x.type === k).value;
    return `${g("day")} ${g("month")}, ${g("hour")}:${g("minute")}`;
  }
  function lineHtml(c, t, lang, name) {
    const why = lang === "bn" && c.reason_bn ? c.reason_bn : c.reason;
    const list = LIST_WORD[listOf(c)];
    const move = c.kind === "list_entered" || c.kind === "list_left" ? (list ? `<span class="chg-list">${esc(t(list))}</span>` : "")
      : c.old_value != null || c.new_value != null ? `<b>${esc(c.old_value ?? "–")}</b> → <b>${esc(c.new_value ?? "–")}</b>` : "";
    const who = c.symbol && c.symbol !== "feedback" ? `<a class="chg-sym" href="#stock/${encodeURIComponent(c.symbol)}">${esc(name ? name(c.symbol) : c.symbol)}</a>` : "";
    return `<li class="chg-li" data-chg="${esc(c.id)}"><span class="chg-dot" aria-hidden="true"></span><span class="chg-what">${esc(t(KIND_WORD[c.kind]))}</span> ${who} ${move} <span class="chg-why">${esc(why)}</span> <time class="muted num">${esc(fmtAt(c.at))}</time></li>`;
  }
  // The strip at the top of Today. Only the first five lines show; the button clears every one.
  function stripHtml(items, o) {
    const t = o.t, list = (items || []).filter(isUnseen);
    if (!list.length) return "";
    const shown = list.slice(0, 5), rest = list.length - shown.length;
    return `<section class="chg-strip" role="status" aria-label="${esc(t("chgT"))}"><div class="chg-head"><span class="chg-dot" aria-hidden="true"></span><h2>${esc(t("chgT"))}</h2>
      <span class="muted">${esc(list.length === 1 ? t("chgOne") : t("chgMany", list.length))}</span><button type="button" class="btn t sm" data-chg-all>${esc(t("chgAllSeen"))}</button></div>
      <ul class="chg-list-ul">${shown.map(c => lineHtml(c, t, o.lang, o.name)).join("")}</ul>${rest > 0 ? `<p class="muted chg-more">${esc(t("chgMore", rest))}</p>` : ""}</section>`;
  }

  // ---- browser glue ----
  function mount(env) {
    const doc = document;
    // The Worth following rows ask the shared client for their row dots, so it runs too (it also sets the tab title count and badge).
    const live = root.SP_LIVE || (root.SP_LIVE = root.SPLive.createClient({
      fetch: (u, i) => fetch(u, i), document: doc, setTimeout: (f, m) => setTimeout(f, m), clearTimeout: x => clearTimeout(x), person: null,
      setBadge: href => { const l = doc.querySelector('link[rel="icon"]'); if (!l) return; l.dataset.plain = l.dataset.plain || l.href; l.href = href || l.dataset.plain; } }));
    live.start();
    let items = [], busy = false, lastStrip = "";
    const read = async () => { try { const r = await fetch("/api/v2/changes?since=", { cache: "no-store" }); if (r.ok) { items = (await r.json()).items || []; paint(); } } catch (e) { /* offline: keep what we have */ } };
    const rail = () => doc.getElementById("rail"), view = () => doc.getElementById("view");
    function paint() {
      if (busy) return; busy = true;
      try {
        const dots = dotsOf(items), r = rail();
        if (r) r.querySelectorAll("a.nav").forEach(a => {
          const tab = (a.getAttribute("href") || "").slice(1), n = dots[tab] || 0, has = a.querySelector(".chg-dot");
          if (n && !has) a.insertAdjacentHTML("beforeend", `<span class="chg-dot nav-dot" role="img" aria-label="${esc(env.t("chgT"))}"></span>`);
          else if (!n && has) has.remove();
        });
        const v = view(), onToday = /^#?(today|calls)?$/.test(location.hash || "");
        if (v) {
          const old = v.querySelector(".chg-strip");
          const html = onToday ? stripHtml(items, { t: env.t, lang: env.lang(), name: env.name }) : "";
          // Touch the page only when the strip's own text changed, or it is missing: every touch wakes the observer below.
          if (!html) { if (old) old.remove(); lastStrip = ""; }
          else if (!old || html !== lastStrip) { if (old) old.remove(); (v.querySelector(".pagewrap") || v).insertAdjacentHTML("afterbegin", html); lastStrip = html; }
        }
      } finally { busy = false; }
    }
    const seen = async body => {
      items = items.map(c => (body.all || (body.ids || []).includes(c.id)) ? { ...c, seen_at: new Date().toISOString() } : c); paint();
      try { await fetch("/api/v2/changes/seen", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }); } catch (e) { /* the next read shows the truth */ }
      read();
    };
    // Opening a tab clears its dot (story 35).
    root.addEventListener("hashchange", () => { const tab = (location.hash || "#today").slice(1).split("/")[0]; const ids = idsForTab(items, tab === "calls" ? "today" : tab); if (ids.length && tab !== "today") seen({ ids }); setTimeout(paint, 0); });
    doc.addEventListener("click", e => { const b = e.target.closest && e.target.closest("[data-chg-all]"); if (b) seen({ all: true }); });
    const again = () => paint();
    [rail(), view()].forEach(el => el && new MutationObserver(again).observe(el, { childList: true, subtree: true }));
    read(); setInterval(() => { if (!doc.hidden) read(); }, 60000);
    doc.addEventListener("visibilitychange", () => { if (!doc.hidden) read(); });
    self.read = read; self.paint = paint;
  }
  const self = { words, dotsOf, idsForTab, stripHtml, lineHtml, tabsOf, mount, read: null, paint: null };
  root.SPChanges = self;
})(typeof window !== "undefined" ? window : globalThis);
