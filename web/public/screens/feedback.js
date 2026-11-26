// T27: the Feedback screen (v2). Plain script: loads in the browser and in Node for tests.
// Posting shows "Received" at once; the VM reads the message into asks; each ask shows its status and the
// read-back in the reader's language; the owner (only) sees Approve and Decline. The server enforces it too.
(function (root) {
  "use strict";
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // Fixed screen words: English and Bengali side by side. app.js merges these into its one word table (T30 gate).
  const words = {
    en: {
      fb2T: "Feedback", fb2S: "Tell us anything you want changed, in any language. We read it and show below what we understood. Only the owner approves changes to a forecast, number, rule, money or tax.",
      fbPrompt: "What should we change, or what is missing?", fbHint: "One line is enough.", send: "Send",
      fbAsked: "What you asked for", fbNone: "You have not sent anything yet.", fbMore: n => `Show ${n} older`, fbLess: "Show fewer",
      stReceived: "Received", stUnderstood: "Understood", stWaiting: "Waiting for approval", stBuilt: "Being built", stDone: "Done", stDeclined: "Declined",
      stepsOf: "Steps", reading: "We are reading this. It appears here within a minute.", cannotRead: "We could not read this one. Please send it again in other words.",
      notSent: "Not sent. Check the connection and press Send again.", sending: "Sending",
      weUnderstood: "We understood", weWill: "What we will do", notMeant: "Not what I meant", notMeantOn: "Marked: we read it wrongly",
      approve: "Approve", decline: "Decline", ownerOnly: "Waiting for the owner to approve.", enTag: "EN",
      delete: "Delete", removed: "Removed.", undo: "Undo", small: "Small", medium: "Medium", large: "Big",
      tagChart: "Chart", tagData: "Numbers", tagNews: "News", tagForecast: "Forecast", tagBug: "Fault", tagWording: "Wording",
    },
    bn: {
      fb2T: "Feedback", fb2S: "যা বদলাতে চান যেকোনো ভাষায় লিখুন। আমরা পড়ে নিচে জানাব কী বুঝেছি। Forecast, সংখ্যা, নিয়ম, টাকা বা কর বদলাতে হলে শুধু মালিক অনুমতি দেন।",
      fbPrompt: "কী বদলাব, বা কী নেই?", fbHint: "এক লাইনই যথেষ্ট।", send: "পাঠান",
      fbAsked: "আপনি যা চেয়েছেন", fbNone: "আপনি এখনও কিছু পাঠাননি।", fbMore: n => `আরও ${n}টা পুরনো দেখুন`, fbLess: "কম দেখুন",
      stReceived: "পেয়েছি", stUnderstood: "বুঝেছি", stWaiting: "অনুমতির অপেক্ষায়", stBuilt: "তৈরি হচ্ছে", stDone: "হয়ে গেছে", stDeclined: "না বলা হয়েছে",
      stepsOf: "ধাপ", reading: "আমরা এটা পড়ছি। এক মিনিটের মধ্যে এখানে দেখা যাবে।", cannotRead: "এটা পড়তে পারিনি। অন্য ভাবে আবার পাঠান।",
      notSent: "পাঠানো হয়নি। সংযোগ দেখে আবার পাঠান চাপুন।", sending: "পাঠানো হচ্ছে",
      weUnderstood: "আমরা যা বুঝেছি", weWill: "আমরা যা করব", notMeant: "আমি এটা বলতে চাইনি", notMeantOn: "চিহ্ন দেওয়া হল: আমরা ভুল বুঝেছি",
      approve: "অনুমতি দিন", decline: "না বলুন", ownerOnly: "মালিকের অনুমতির অপেক্ষায়।", enTag: "EN",
      delete: "মুছুন", removed: "মুছে ফেলা হল।", undo: "ফিরিয়ে আনুন", small: "ছোট", medium: "মাঝারি", large: "বড়",
      tagChart: "চার্ট", tagData: "সংখ্যা", tagNews: "খবর", tagForecast: "Forecast", tagBug: "ত্রুটি", tagWording: "লেখা",
    },
  };

  const STEPS = ["received", "understood", "waiting_for_approval", "being_built", "done"];
  const STATUS = {
    received: ["stReceived", "v-none"], understood: ["stUnderstood", "v-watch"], waiting_for_approval: ["stWaiting", "v-hold"],
    being_built: ["stBuilt", "v-weak"], done: ["stDone", "v-buy"], declined: ["stDeclined", "v-sell"],
  };
  const TAG = { chart: "tagChart", data: "tagData", news: "tagNews", forecast: "tagForecast", bug: "tagBug", wording: "tagWording" };
  const SIZE = { small: "small", medium: "medium", large: "large" };

  function fmtAt(at) {
    const d = new Date(at); if (isNaN(d)) return "";
    const p = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false }).formatToParts(d);
    const g = k => p.find(x => x.type === k).value;
    return `${g("day")} ${g("month")}, ${g("hour")}:${g("minute")}`;
  }

  function trail(status, t) {
    const at = STEPS.indexOf(status);
    return `<div class="fb-trail" role="img" aria-label="${esc(t("stepsOf"))}: ${esc(t(STATUS[status][0]))}">${STEPS.map((s, i) =>
      `<span class="${status === "declined" ? "" : i < at ? "done" : i === at ? "now" : ""}">${esc(t(STATUS[s][0]))}</span>`).join("")}</div>`;
  }

  function askHtml(a, o) {
    const { t, lang, person } = o;
    const [lab, cls] = STATUS[a.status] || STATUS.received;
    const bn = lang === "bn";
    const line = bn ? (a.line_bn || a.line_en) : a.line_en;
    const tag = bn && !a.line_bn ? ` <span class="fb-entag" title="No Bengali yet">${esc(t("enTag"))}</span>` : "";
    const wait = a.status === "waiting_for_approval";
    const acts = wait && person === "owner"
      ? `<div class="fb-acts"><button class="btn f" type="button" data-fb-act="approve" data-id="${esc(a.id)}"><span class="ms">check</span>${esc(t("approve"))}</button><button class="btn o" type="button" data-fb-act="decline" data-id="${esc(a.id)}"><span class="ms">close</span>${esc(t("decline"))}</button></div>`
      : wait ? `<p class="fb-note">${esc(t("ownerOnly"))}</p>` : "";
    const nm = a.not_meant
      ? `<span class="fb-nm on">${esc(t("notMeantOn"))}</span>`
      : `<button class="btn x sm" type="button" data-fb-act="notmeant" data-id="${esc(a.id)}">${esc(t("notMeant"))}</button>`;
    return `<div class="fb-ask" data-ask="${esc(a.id)}" data-st="${esc(a.status)}">
      <div class="fb-ask-top"><span class="chip ${cls}">${esc(t(lab))}</span>${a.tag && TAG[a.tag] ? `<span class="fb-meta">${esc(t(TAG[a.tag]))}</span>` : ""}${SIZE[a.size] ? `<span class="fb-meta">${esc(t(SIZE[a.size]))}</span>` : ""}</div>
      <p class="fb-read"><span class="fb-k">${esc(t("weUnderstood"))}</span> ${esc(line)}${tag}</p>
      ${a.plan ? `<p class="fb-plan"><span class="fb-k">${esc(t("weWill"))}</span> ${esc(a.plan)}</p>` : ""}
      ${a.status === "declined" ? "" : trail(a.status, t)}${acts}<div class="fb-ask-foot">${nm}</div></div>`;
  }

  function itemHtml(f, o) {
    const { t } = o;
    const bad = f.local === "failed", sending = f.local === "sending";
    const [lab, cls] = bad ? ["notSent", "v-sell"] : sending ? ["sending", "v-none"] : f.asks.length ? [null, null] : f.status === "failed" ? ["cannotRead", "v-sell"] : ["stReceived", "v-none"];
    const head = lab ? `<span class="chip ${cls}">${esc(t(lab === "cannotRead" ? "stDeclined" : lab))}</span>` : `<span class="chip v-watch">${esc(t("stUnderstood"))}</span>`;
    const body = bad ? `<p class="fb-note">${esc(t("notSent"))}</p>`
      : f.asks.length ? f.asks.map(a => askHtml(a, o)).join("")
      : f.status === "failed" ? `<p class="fb-note">${esc(t("cannotRead"))}</p>` : `<p class="fb-note">${esc(t("reading"))}</p>`;
    return `<article class="fb-item" data-fb="${esc(f.id)}"><div class="fb-item-top">${head}<time class="muted num">${esc(fmtAt(f.created_at))}</time><button class="btn x sm fb-del" type="button" data-fb-act="hide" data-id="${esc(f.id)}"><span class="ms">delete</span>${esc(t("delete"))}</button></div>
      <p class="fb-said">${esc(f.text)}</p>${body}</article>`;
  }

  function listHtml(items, o) {
    const { t, more } = o;
    if (!items.length) return `<p class="muted fb-none">${esc(t("fbNone"))}</p>`;
    const shown = items.slice(0, more ? 50 : 5);
    return `<div class="fb-list">${shown.map(f => itemHtml(f, o)).join("")}</div>` +
      (items.length > 5 ? `<div class="more"><button class="btn t" type="button" data-fb-act="more">${esc(more ? t("fbLess") : t("fbMore", items.length - 5))}</button></div>` : "");
  }

  // The part of the page that changes on every poll. The box and its text stay put so nothing typed is lost.
  function pageHtml(t) {
    return `<header class="page-h rise"><h1 class="disp">${esc(t("fb2T"))}</h1><p>${esc(t("fb2S"))}</p></header>
      <div class="fb-box"><label class="fb-q" for="fbt">${esc(t("fbPrompt"))}</label><textarea id="fbt" placeholder="${esc(t("fbHint"))}"></textarea><div><button class="btn f" type="button" data-fb-act="send"><span class="ms">rate_review</span>${esc(t("send"))}</button></div></div>
      <div class="secttl"><h2>${esc(t("fbAsked"))}</h2></div><div id="fb-live"></div>`;
  }

  const BUSY_MS = 3000, ASKS_MS = 8000, QUIET_MS = 30000;
  function createScreen(o) {
    const F = o.fetch, ST = o.setTimeout, CT = o.clearTimeout, store = o.store || { get: () => [], set: () => {} };
    let person = null, items = [], timer = null, more = false, local = [], n = 0, hidden = new Set(store.get() || []);
    const j = async (url, init) => { const r = await F(url, init); if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); };
    const view = () => {
      const all = local.concat(items).filter(f => !hidden.has(f.id));
      o.paint(listHtml(all, { t: o.t, lang: o.lang(), person, more }), all);
    };
    const busy = () => local.some(f => f.local === "sending") || items.some(f => f.status === "received" || f.status === "reading");
    const live = () => items.some(f => f.asks.some(a => ["received", "understood", "being_built"].includes(a.status)));
    function schedule() {
      if (timer) CT(timer);
      timer = ST(() => { timer = null; if (o.alive()) return load().then(schedule); }, busy() ? BUSY_MS : live() ? ASKS_MS : QUIET_MS);
    }
    async function load() {
      try { const r = await j("/api/v2/feedback"); items = (r.items || []).map(f => ({ ...f, asks: f.asks || [] })); local = local.filter(f => f.local === "failed"); view(); return true; }
      catch (e) { return false; }
    }
    const self = {
      async start() {
        try { person = (await j("/api/me")).person || null; } catch (e) { person = null; }
        await load(); schedule();
      },
      stop() { if (timer) CT(timer); timer = null; },
      async post(text) {
        text = String(text || "").trim(); if (!text) return null;
        const id = "local-" + (++n), at = new Date().toISOString();
        local = local.filter(f => f.local !== "failed");
        local.unshift({ id, text, status: "received", created_at: at, asks: [], local: "sending" }); view();
        try {
          await j("/api/v2/feedback", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ text }) });
        } catch (e) { local = local.map(f => f.id === id ? { ...f, local: "failed" } : f); view(); return false; }
        await load(); schedule(); return true;
      },
      async act(kind, id) {
        if (kind === "more") { more = !more; return view(); }
        if (kind === "hide") { hidden.add(id); store.set([...hidden]); view(); if (o.toast) o.toast(o.t("removed"), () => { hidden.delete(id); store.set([...hidden]); view(); }); return; }
        const find = () => items.flatMap(f => f.asks).find(a => a.id === id);
        try {
          if (kind === "notmeant") { await j(`/api/v2/asks/${encodeURIComponent(id)}/not-meant`, { method: "POST" }); const a = find(); if (a) a.not_meant = true; }
          else if (kind === "approve" || kind === "decline") {
            if (person !== "owner") return;   // the father has no such button; this is the belt to the server's braces
            const r = await j(`/api/v2/asks/${encodeURIComponent(id)}/decide`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ decision: kind }) });
            const a = find(); if (a) a.status = r.status;
          } else return;
        } catch (e) { /* the next poll shows the true state */ }
        view(); await load(); schedule();
      },
      person: () => person,
    };
    return self;
  }

  // Browser glue: paint into the page, listen once on the view.
  let current = null;
  if (typeof document !== "undefined") document.addEventListener("visibilitychange", () => { if (current && !document.hidden && document.getElementById("fb-live")) current.start(); });
  function mount(env) {
    if (current) current.stop();
    const live = document.getElementById("fb-live"); if (!live) return;
    const store = { get() { try { return JSON.parse(localStorage.getItem("sp-fbhide") || "[]"); } catch (e) { return []; } }, set(v) { try { localStorage.setItem("sp-fbhide", JSON.stringify(v)); } catch (e) { /* fine */ } } };
    const sc = current = createScreen({ fetch: (u, i) => fetch(u, { cache: "no-store", ...i }), t: env.t, lang: env.lang, toast: env.toast, store,
      setTimeout: window.setTimeout.bind(window), clearTimeout: window.clearTimeout.bind(window),
      alive: () => live.isConnected && !document.hidden,
      paint: h => { live.innerHTML = h; } });
    document.getElementById("view").onclick = async e => {
      const b = e.target.closest("[data-fb-act]"); if (!b) return;
      const k = b.dataset.fbAct;
      if (k === "send") { const ta = document.getElementById("fbt"); const text = ta.value.trim(); if (!text) { ta.focus(); return; } ta.value = ""; if ((await sc.post(text)) === false) ta.value = text; return; }
      sc.act(k, b.dataset.id);
    };
    sc.start();
  }

  root.SPFeedback = { words, pageHtml, listHtml, askHtml, createScreen, mount, STEPS };
})(typeof window !== "undefined" ? window : globalThis);
