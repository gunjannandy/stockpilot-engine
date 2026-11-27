// AUDIT #23: "Market news must always be live, and the special stocks list too." The collector gathers news every 15 minutes and the
// VM tags and ranks it into D1, but no screen read it: Market & news showed only the nightly numbers. This is the smallest screen that
// does: the day's top news from /api/v2/news with its age, and the "In today's news" stocks from /api/v2/lists/in_the_news, both
// re-read every few minutes while the tab is open, each saying how old the newest item is and when we last looked.
// The full news screen (thumbnails, timeline, sector strip) is ticket T31; this block stays above it.
(function (root) {
  "use strict";
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const POLL_MS = 5 * 60 * 1000, SHOW = 8;

  const words = {
    en: {
      nlT: "Market news, live", nlS: "Collected every 15 minutes from the exchanges and the news sites. Ranked by how much it matters to your stocks.",
      nlNewest: m => `Newest item ${m}`, nlChecked: m => `checked ${m}`, nlNone: "No news has come in yet. The collector runs every 15 minutes.", nlFail: "The news did not load. It will try again in a few minutes.",
      nlStocks: "In today's news", nlStocksNone: "No stock is in the news right now.", nlHeld: "You hold it", nlSources: n => `${n} sources`,
      nlGood: "Good", nlBad: "Bad", nlMixed: "Mixed", nlRefresh: "Refresh", nlChangesCall: "Changes our view",
      nlAgoNow: "just now", nlAgoMin: n => `${n} min ago`, nlAgoH: n => `${n} h ago`, nlAgoD: n => `${n} d ago`,
    },
    bn: {
      nlT: "বাজারের খবর, সরাসরি", nlS: "প্রতি ১৫ মিনিটে এক্সচেঞ্জ আর খবরের সাইট থেকে জোগাড় করা হয়। আপনার স্টকের কাছে কতটা জরুরি, সেই হিসাবে সাজানো।",
      nlNewest: m => `সবচেয়ে নতুন খবর ${m}`, nlChecked: m => `দেখা হয়েছে ${m}`, nlNone: "এখনও কোনো খবর আসেনি। collector প্রতি ১৫ মিনিটে চলে।", nlFail: "খবর আনা যায়নি। কয়েক মিনিট পরে আবার চেষ্টা হবে।",
      nlStocks: "আজকের খবরে", nlStocksNone: "এই মুহূর্তে কোনো স্টক খবরে নেই।", nlHeld: "আপনার কাছে আছে", nlSources: n => `${n}টি সূত্র`,
      nlGood: "ভালো", nlBad: "খারাপ", nlMixed: "মিশ্র", nlRefresh: "আবার আনুন", nlChangesCall: "আমাদের মত বদলায়",
      nlAgoNow: "এইমাত্র", nlAgoMin: n => `${n} মিনিট আগে`, nlAgoH: n => `${n} ঘণ্টা আগে`, nlAgoD: n => `${n} দিন আগে`,
    },
  };

  function ago(at, now, t) {
    const ms = now - Date.parse(at); if (!(ms >= 0)) return t("nlAgoNow");
    const m = Math.floor(ms / 60000);
    return m < 1 ? t("nlAgoNow") : m < 60 ? t("nlAgoMin", m) : m < 1440 ? t("nlAgoH", Math.floor(m / 60)) : t("nlAgoD", Math.floor(m / 1440));
  }
  const dirWord = d => d === "good" ? "nlGood" : d === "bad" ? "nlBad" : "nlMixed";
  const hasDir = d => d === "good" || d === "bad" || d === "mixed";   // an untagged item is stored as "none": no mark

  function itemHtml(it, o) {
    const { t, lang, now, name, held } = o;
    const line = (lang === "bn" && it.line_bn) || it.line_en;
    const chips = (it.tags || []).filter(x => x.relation === "self" || x.changes_call).slice(0, 4).map(x =>
      `<a class="nl-chip" href="#stock" data-open="${esc(x.symbol)}">${esc(name ? name(x.symbol) : x.symbol)}${held && held(x.symbol) ? ` <span class="muted">· ${esc(t("nlHeld"))}</span>` : ""}</a>`).join("");
    return `<li class="nl-item" data-tier="${esc(it.rank?.tier || "low")}"><div class="nl-top"><span class="nl-dir nl-${esc(it.direction)}" ${hasDir(it.direction) ? "" : "hidden"}>${esc(t(dirWord(it.direction)))}</span>
      <a class="nl-title" href="${esc(it.link)}" target="_blank" rel="noopener noreferrer">${esc(it.title)}</a></div>
      ${line ? `<p class="nl-line">${esc(line)}${it.tags?.some(x => x.changes_call) ? ` <b>${esc(t("nlChangesCall"))}</b>` : ""}</p>` : ""}
      <div class="nl-meta muted"><span>${esc(it.source)}</span><span>·</span><time datetime="${esc(it.published_at)}">${esc(ago(it.published_at, now, t))}</time>${it.source_count > 1 ? `<span>·</span><span>${esc(t("nlSources", it.source_count))}</span>` : ""}</div>${chips ? `<div class="nl-chips">${chips}</div>` : ""}</li>`;
  }

  // news: the /api/v2/news answer; stocks: the /api/v2/lists/in_the_news answer; either may be null when it failed.
  function blockHtml(news, stocks, o) {
    const { t, lang, now, name, held } = o;
    const items = (news && news.items) || [];
    const newest = items.reduce((a, i) => (!a || Date.parse(i.published_at) > Date.parse(a) ? i.published_at : a), null);
    const head = `<div class="nl-head"><h2>${esc(t("nlT"))}</h2><span class="muted nl-stamp">${newest ? esc(t("nlNewest", ago(newest, now, t))) + " · " : ""}${esc(t("nlChecked", ago(new Date(o.checkedAt || now).toISOString(), now, t)))}</span><button type="button" class="btn t sm" data-nl-refresh>${esc(t("nlRefresh"))}</button></div><p class="muted nl-sub">${esc(t("nlS"))}</p>`;
    const body = !news ? `<p class="muted">${esc(t("nlFail"))}</p>` : !items.length ? `<p class="muted">${esc(t("nlNone"))}</p>` : `<ul class="nl-list">${items.slice(0, SHOW).map(i => itemHtml(i, o)).join("")}</ul>`;
    const list = (stocks && stocks.items) || [];
    const side = `<div class="nl-stocks"><h3>${esc(t("nlStocks"))}</h3>${list.length ? `<ul>${list.map(s => `<li><a href="#stock" data-open="${esc(s.symbol)}">${esc(name ? name(s.symbol) : s.symbol)}</a> <span class="muted">${esc((lang === "bn" && s.reason_bn) || s.reason || "")}</span></li>`).join("")}</ul>` : `<p class="muted">${esc(t("nlStocksNone"))}</p>`}</div>`;
    return `<section class="nl" aria-label="${esc(t("nlT"))}">${head}<div class="nl-grid"><div>${body}</div>${side}</div></section>`;
  }

  function mount(env) {
    const doc = document;
    let timer = null, news = null, stocks = null, checkedAt = Date.now();
    const host = () => doc.getElementById("newslive");
    const paint = () => { const h = host(); if (h) h.innerHTML = blockHtml(news, stocks, { t: env.t, lang: env.lang(), now: Date.now(), name: env.name, held: env.held, checkedAt }); };
    async function load() {
      const get = async u => { try { const r = await fetch(u, { cache: "no-store" }); return r.ok ? r.json() : null; } catch (e) { return null; } };
      const [n, s] = await Promise.all([get("/api/v2/news?limit=30"), get("/api/v2/lists/in_the_news")]);
      news = n; stocks = s; checkedAt = Date.now(); paint();
    }
    const tick = () => { if (!host()) { timer = null; return; } if (!doc.hidden) load(); timer = setTimeout(tick, POLL_MS); };
    if (timer) clearTimeout(timer);
    paint(); load(); timer = setTimeout(tick, POLL_MS);
    const h = host(); if (h) h.onclick = e => { if (e.target.closest("[data-nl-refresh]")) load(); };
  }

  root.SPNewsLive = { words, ago, itemHtml, blockHtml, mount };
})(typeof window !== "undefined" ? window : globalThis);
