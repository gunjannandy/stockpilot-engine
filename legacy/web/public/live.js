// T21: live data client, polling rules, job progress and notification rules N1-N9.
// Behaviour only: no look. Plain script (browser) that also loads in Node for tests.
(function (root) {
  "use strict";
  const MIN = 60 * 1000, DAY = 24 * 60 * MIN;
  const JOB_POLL_MS = 3000, IDLE_POLL_MS = 5 * MIN, QUOTE_POLL_MS = 5 * MIN, TOAST_MS = 8000, STRIP_DAYS = 7;
  // N: which nav tab a kind of change belongs to. Anything else earns no dot.
  const NAV_OF = { call_changed: "calls", chance_moved: "calls", level_crossed: "calls", forecast_ready: "calls", list_entered: "lists", list_left: "lists", ask_status: "feedback" };
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const relevant = items => (items || []).filter(i => NAV_OF[i.kind]);
  const unseen = items => relevant(items).filter(i => !i.seen_at);

  function navCountsOf(items) {
    const o = {};
    unseen(items).forEach(i => { const t = NAV_OF[i.kind]; o[t] = (o[t] || 0) + 1; });
    return o;
  }
  // The strip on Today: unseen changes from the last 7 days. Older ones stay in the stock's history.
  function stripItems(items, now) {
    return unseen(items).filter(i => now - Date.parse(i.at) <= STRIP_DAYS * DAY);
  }
  const tabTitleOf = (base, n) => n > 0 ? `(${n}) ${base}` : base;
  function badgeHref(n) {
    if (!(n > 0)) return "";
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="7" fill="#1f2a37"/><circle cx="23" cy="9" r="9" fill="#f2b705"/><text x="23" y="13" font-size="12" font-family="sans-serif" font-weight="700" text-anchor="middle" fill="#000">${n > 9 ? "9+" : n}</text></svg>`;
    return "data:image/svg+xml," + encodeURIComponent(svg);
  }

  // ---- pieces of screen: strings only, so the look can change without touching the rules
  const DOT = '<span class="chg-dot" role="img" aria-label="changed" title="Changed since you last looked"></span>';
  function rowMarks({ dot, newsNoChange }) {
    return (dot ? DOT : "") + (newsNoChange && !dot
      ? '<span class="news-mark"><span class="material-symbols-rounded" aria-hidden="true">newspaper</span><button type="button" data-update>Update</button></span>' : "");
  }
  function fmtAt(at) {
    const d = new Date(at); if (isNaN(d)) return "";
    const p = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false }).formatToParts(d);
    const g = t => p.find(x => x.type === t).value;
    return `${g("day")} ${g("month")}, ${g("hour")}:${g("minute")}`;
  }
  function changeBandHtml(c, lang) {
    if (!c) return "";
    const why = lang === "bn" && c.reason_bn ? c.reason_bn : c.reason;
    const move = c.old_value != null || c.new_value != null ? `<b>${esc(c.old_value ?? "–")}</b> → <b>${esc(c.new_value ?? "–")}</b>` : "";
    return `<div class="chg-band" data-kind="${esc(c.kind)}"><time>${esc(fmtAt(c.at))}</time> ${move} <span class="why">${esc(why)}</span></div>`;
  }
  const staleChip = stale => stale ? '<span class="chip amber" title="This forecast is out of date">Out of date</span>' : "";
  const healthCount = (n, person) => person === "owner" ? (n | 0) : 0;   // N: owner-only red count

  function jobProgressHtml({ job, lines }, lang) {
    const rows = (lines || []).slice().sort((a, b) => a.seq - b.seq).map(l =>
      `<li data-state="${esc(l.state)}">${esc(lang === "bn" && l.text_bn ? l.text_bn : l.text)}</li>`).join("");
    let tail = "";
    if (job.status === "failed") tail = `<p class="job-err">${esc(lang === "bn" && job.error_bn ? job.error_bn : job.error || "Something went wrong")}</p><button type="button" data-retry>Try again</button>`;
    else if (job.status === "done" && job.result) tail = `<p class="job-ok">${esc(job.result)}</p>`;
    return `<div class="job-progress" data-state="${esc(job.status)}"><ul>${rows}</ul>${tail}</div>`;
  }

  // T15: "price 14 min old · refreshing". The age is always shown; null means we hold no price yet.
  function priceLabel(quote, refreshing) {
    let base = "price not available yet";
    if (quote) {
      const sec = Math.max(0, quote.age_seconds | 0);
      base = sec < 60 ? "price just now"
        : sec < 3600 ? `price ${Math.floor(sec / 60)} min old`
        : sec < 86400 ? `price ${Math.floor(sec / 3600)} h old`
        : `price ${Math.floor(sec / 86400)} day${Math.floor(sec / 86400) > 1 ? "s" : ""} old`;
    }
    return refreshing ? base + " · refreshing" : base;
  }

  // ---- the client
  function createClient(o) {
    const F = o.fetch, doc = o.document, ST = o.setTimeout, CT = o.clearTimeout, now = o.now || Date.now;
    const base = o.title || "stockpilot", person = o.person;
    let items = [], listeners = [], idleTimer = null, started = false, setHref = o.setBadge || (() => {});
    const watching = new Map();   // job id -> timer id or null
    const emit = e => listeners.forEach(f => f(e));
    const visible = () => !doc.hidden;
    const j = async (url, init) => { const r = await F(url, init); if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); };

    const self = {
      on(f) { listeners.push(f); },
      hasDot: sym => unseen(items).some(i => i.symbol === sym),
      unseenCount: () => unseen(items).length,
      navCounts: () => navCountsOf(items),
      strip: () => stripItems(items, now()),
      changeFor: sym => unseen(items).find(i => i.symbol === sym) || null,
      tabTitle: b => tabTitleOf(b || base, unseen(items).length),
      badgeHref: () => badgeHref(unseen(items).length),
      async refreshChanges() {
        try { const r = await j("/api/v2/changes?since="); items = r.items || []; paint(); emit({ type: "changes" }); } catch (e) { emit({ type: "offline" }); }
      },
      async markSeen(body) {
        const keep = items;   // optimistic: clear at once, put back if the server says no
        items = items.map(i => (body.all || (body.symbol && i.symbol === body.symbol) || (body.ids || []).includes(i.id)) ? { ...i, seen_at: new Date(now()).toISOString() } : i);
        paint(); emit({ type: "changes" });
        try { await j("/api/v2/changes/seen", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }); }
        catch (e) { items = keep; paint(); emit({ type: "changes" }); }
      },
      openStock: sym => self.markSeen({ symbol: sym }),
      markAllSeen: () => self.markSeen({ all: true }),
      watchJob(id) { if (watching.has(id)) return; watching.set(id, null); if (visible()) pollJob(id); },
      start() {
        if (started) return; started = true;
        doc.addEventListener("visibilitychange", () => {
          if (visible()) { self.refreshChanges(); [...watching.keys()].forEach(pollJob); schedule(); }
          else { CT(idleTimer); idleTimer = null; watching.forEach((t, id) => { if (t) CT(t); watching.set(id, null); }); }
        });
        if (visible()) { self.refreshChanges(); schedule(); }
      },
    };
    // T15: an open stock shows the stored price with its age at once, asks the server to refresh it, swaps the new one in,
    // and asks again every 5 minutes while the tab is visible. If the refresh fails the old price stays, with its age.
    let quoteSym = null, quoteTimer = null, quoteWired = false;
    async function pollQuote() {
      CT(quoteTimer); quoteTimer = null;
      const sym = quoteSym; if (!sym || !visible()) return;
      const url = "/api/v2/quotes?symbols=" + encodeURIComponent(sym);
      let cur = null;
      try { cur = ((await j(url)).quotes || [])[0] || null; } catch (e) { /* keep what we have */ }
      if (quoteSym !== sym) return;
      emit({ type: "quote", symbol: sym, quote: cur, refreshing: true });
      try { cur = ((await j(url + "&refresh=1")).quotes || [])[0] || cur; } catch (e) { /* the old price stays */ }
      if (quoteSym !== sym) return;
      emit({ type: "quote", symbol: sym, quote: cur, refreshing: false });
      if (visible()) quoteTimer = ST(pollQuote, QUOTE_POLL_MS);
    }
    self.openQuote = sym => {
      quoteSym = sym;
      if (!quoteWired) { quoteWired = true; doc.addEventListener("visibilitychange", () => { if (!quoteSym) return; if (visible()) pollQuote(); else { CT(quoteTimer); quoteTimer = null; } }); }
      return pollQuote();
    };
    self.closeQuote = () => { quoteSym = null; CT(quoteTimer); quoteTimer = null; };

    function paint() { doc.title = tabTitleOf(base, unseen(items).length); setHref(badgeHref(unseen(items).length)); }
    function schedule() {
      CT(idleTimer); idleTimer = null;
      if (!visible()) return;
      idleTimer = ST(() => { if (visible()) { self.refreshChanges(); schedule(); } }, IDLE_POLL_MS);
    }
    async function pollJob(id) {
      const t0 = watching.get(id); if (t0) CT(t0);
      watching.set(id, null);
      if (!visible()) return;   // nothing runs while hidden; the tab coming back restarts it
      let r; try { r = await j("/api/v2/jobs/" + encodeURIComponent(id)); } catch (e) { r = null; }
      if (!watching.has(id)) return;
      if (r) emit({ type: "job", id, ...r });
      const st = r && r.job.status;
      if (st === "done" || st === "failed") {
        watching.delete(id);
        const what = r.job.result || r.job.kind;
        emit(st === "done" ? { type: "toast", id, text: `${what} is ready`, action: "Open", ms: TOAST_MS }
          : { type: "toast", id, text: r.job.error || "That did not work", action: "Try again", ms: TOAST_MS });
        self.refreshChanges();
        return;
      }
      if (visible()) watching.set(id, ST(() => pollJob(id), JOB_POLL_MS));
    }
    return self;
  }

  const API = { createClient, priceLabel, navCountsOf, stripItems, tabTitleOf, badgeHref, rowMarks, changeFor: undefined, changeBandHtml, staleChip, healthCount, jobProgressHtml, NAV_OF, JOB_POLL_MS, IDLE_POLL_MS };
  root.SPLive = API;
})(typeof window !== "undefined" ? window : globalThis);
