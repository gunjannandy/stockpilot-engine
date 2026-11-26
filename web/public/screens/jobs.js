// T28: the Jobs screen. Plain script (browser) that also loads in Node for tests.
// Pure builders take data and give HTML strings; `mount` does the fetching. app.js only calls SPJobs.page / SPJobs.mount.
(function (root) {
  "use strict";
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const MIN = 60000;

  // Every job kind in schemas/live-contract.json: plain name, who runs it, and an icon.
  const KINDS = {
    sync: ["Sync from Zerodha", "vm_private", "sync"], analyse: ["Analyse a stock", "vm_model", "query_stats"],
    refresh_call: ["Update a forecast", "vm_model", "refresh"], feedback_read: ["Read your feedback", "vm_model", "rate_review"],
    news_tag: ["Sort the news", "vm_model", "newspaper"], news_rank: ["Rank news for your stocks", "vm_private", "newspaper"],
    load_stock: ["Load a new stock", "github_public", "download"], news_collect: ["Collect market news", "github_public", "newspaper"],
    history_backfill: ["Load price history", "github_public", "history"], nightly: ["Nightly forecasts", "github_public", "schedule"],
    weekly_review: ["Weekly review of our calls", "vm_model", "fact_check"], backup: ["Back up the records", "vm_private", "savings"],
    watchlist_add: ["Add to watchlist", "vm_private", "star"],
    watchlist_remove: ["Remove from watchlist", "vm_private", "star_border"],
    budget_set: ["Set the budget", "vm_private", "savings"],
    allocation_approve: ["Approve the target mix", "vm_private", "check_circle"],
    refresh_docs: ["Read your documents again", "vm_private", "description"],
    rerun: ["Run a job again", "vm_private", "replay"],
    build_tax_pack: ["Build the tax pack", "vm_private", "receipt_long"],
    not_now: ["Keep out of calls for now", "vm_private", "snooze"],
    snooze: ["Hide calls for a stock", "vm_private", "snooze"],
    dismiss: ["Dismiss calls for a stock", "vm_private", "block"],
    not_now_undo: ["Undo a hidden call", "vm_private", "undo"],
    learned_forget: ["Forget a lesson", "vm_private", "delete"],
    long_term_mark: ["Mark as held for years", "vm_private", "hourglass_top"],
  };
  const words = {
    en: {
      jobsT: "Jobs", jobsP: "Everything we are doing for you: waiting, running, finished and failed, including the scheduled ones. Pressing a button anywhere starts a job and it shows here.",
      jRunning: "Running now", jActive: "Running and waiting", jWaiting: "Waiting", jFailed: "Did not finish", jDone: "Done today", jRecent: "Recent", jNoneRun: "Nothing is running.", jNoneAll: "No jobs yet.",
      jRerun: "Try again", jStarted: "Started", jQueued: "Waiting to start", jTook: "Took", jMinS: "min", jResult: "Result", jWhen: "When", jJob: "Job", jKind: "Kind", jState: "State",
      jsRunning: "Running", jsQueued: "Waiting", jsDone: "Done", jsFailed: "Did not finish", jAskedBy: "Asked by", jByOwner: "you", jByFather: "your father", jBySystem: "scheduled",
      jBudget: "Daily write budget", jBudgetP: "How much we have saved today out of what the free database allows. Plenty is kept back for your own taps.", jBudgetOf: (n, m) => `${n} of ${m}`,
      jbOk: "Fine", jbWarn: "Getting high", jbStopped: "Stopped for today", jMinutes: "Work done today", jMinutesP: "Time all jobs together ran today.", jMinutesV: m => `${m} min`,
      jOnlyOwner: "Only the owner sees this page.", jOffline: "Cannot reach the jobs list right now. It will try again.", jOk: "Started again", jLoading: "Loading jobs",
      jAgo: m => m < 1 ? "just now" : m < 60 ? `${m} min ago` : m < 1440 ? `${Math.floor(m / 60)} h ago` : `${Math.floor(m / 1440)} d ago`, jDash: "–",
      jFailedWhy: "Why it stopped", jSteps: "Steps",
    },
    bn: {
      jobsT: "Jobs", jobsP: "আপনার জন্য আমরা যা যা করছি: অপেক্ষায়, চলছে, শেষ এবং ব্যর্থ, নির্ধারিত কাজগুলোও। যে কোনো জায়গায় button চাপলে একটা job শুরু হয় এবং এখানে দেখা যায়।",
      jRunning: "এখন চলছে", jActive: "চলছে ও অপেক্ষায়", jWaiting: "অপেক্ষায়", jFailed: "শেষ হয়নি", jDone: "আজ শেষ হয়েছে", jRecent: "সাম্প্রতিক", jNoneRun: "এখন কিছু চলছে না।", jNoneAll: "এখনও কোনো job নেই।",
      jRerun: "আবার চেষ্টা করুন", jStarted: "শুরু", jQueued: "শুরুর অপেক্ষায়", jTook: "সময় লেগেছে", jMinS: "মিনিট", jResult: "ফল", jWhen: "কখন", jJob: "Job", jKind: "ধরন", jState: "অবস্থা",
      jsRunning: "চলছে", jsQueued: "অপেক্ষায়", jsDone: "হয়ে গেছে", jsFailed: "শেষ হয়নি", jAskedBy: "চেয়েছেন", jByOwner: "আপনি", jByFather: "আপনার বাবা", jBySystem: "নির্ধারিত",
      jBudget: "দৈনিক লেখার সীমা", jBudgetP: "বিনামূল্যের database আজ যতটা লিখতে দেয়, তার কতটা আমরা ব্যবহার করেছি। আপনার নিজের চাপের জন্য অনেকটা আলাদা রাখা আছে।", jBudgetOf: (n, m) => `${m}-এর মধ্যে ${n}`,
      jbOk: "ঠিক আছে", jbWarn: "বেড়ে যাচ্ছে", jbStopped: "আজকের মতো বন্ধ", jMinutes: "আজকের কাজ", jMinutesP: "আজ সব job মিলিয়ে যতক্ষণ চলেছে।", jMinutesV: m => `${m} মিনিট`,
      jOnlyOwner: "এই পাতা শুধু মালিক দেখতে পান।", jOffline: "এখন job-এর তালিকা পাওয়া যাচ্ছে না। আবার চেষ্টা করবে।", jOk: "আবার শুরু হয়েছে", jLoading: "Job আসছে",
      jAgo: m => m < 1 ? "এইমাত্র" : m < 60 ? `${m} মিনিট আগে` : m < 1440 ? `${Math.floor(m / 60)} ঘণ্টা আগে` : `${Math.floor(m / 1440)} দিন আগে`, jDash: "–",
      jFailedWhy: "কেন থেমেছে", jSteps: "ধাপ",
    },
    kinds_bn: {
      sync: "Zerodha থেকে sync", analyse: "একটা stock-এর বিশ্লেষণ", refresh_call: "Forecast হালনাগাদ", feedback_read: "আপনার feedback পড়া", news_tag: "খবর সাজানো",
      news_rank: "আপনার stock-এর খবর সাজানো", load_stock: "নতুন stock আনা", news_collect: "বাজারের খবর জোগাড়", history_backfill: "দামের ইতিহাস আনা", nightly: "রাতের forecast",
      weekly_review: "আমাদের call-এর সাপ্তাহিক পর্যালোচনা", backup: "রেকর্ডের backup",
      watchlist_add: "Watchlist-এ যোগ",
      watchlist_remove: "Watchlist থেকে সরানো",
      budget_set: "Budget ঠিক করা",
      allocation_approve: "লক্ষ্যের ভাগ অনুমোদন",
      refresh_docs: "কাগজপত্র আবার পড়া",
      rerun: "কাজ আবার চালানো",
      build_tax_pack: "Tax pack বানানো",
      not_now: "এখনকার মতো call থেকে বাদ",
      snooze: "Stock-এর call লুকানো",
      dismiss: "Stock-এর call বাতিল",
      not_now_undo: "লুকানো call ফেরানো",
      learned_forget: "শিক্ষা ভোলা",
      long_term_mark: "বছরের পর বছর ধরে রাখার চিহ্ন",
    },
  };
  const T = (lang, k, ...a) => { const v = (words[lang] && words[lang][k]) ?? words.en[k]; return typeof v === "function" ? v(...a) : (v ?? k); };
  const kindName = (job, lang) => {
    const base = lang === "bn" && words.kinds_bn[job.kind] ? words.kinds_bn[job.kind] : (KINDS[job.kind] ? KINDS[job.kind][0] : job.kind);
    const p = job.payload || {};
    return p.symbol ? `${base}: ${p.symbol}` : base;
  };
  const ms = t => { const x = Date.parse(t); return isNaN(x) ? null : x; };
  const minutesBetween = (a, b) => { const x = ms(a), y = ms(b); return x == null || y == null ? null : Math.max(0, Math.round((y - x) / MIN)); };
  const istDay = t => { const x = ms(t); return x == null ? "" : new Date(x + 330 * MIN).toISOString().slice(0, 10); };
  const ago = (t, now, lang) => { const x = ms(t); return x == null ? T(lang, "jDash") : T(lang, "jAgo", Math.max(0, Math.floor((now - x) / MIN))); };

  // Plain failure words: never show a stack trace or a code to the father.
  function failWords(job, lang) {
    const e = lang === "bn" && job.error_bn ? job.error_bn : job.error;
    return String(e || (lang === "bn" ? "কিছু একটা ভুল হয়েছে। আবার চেষ্টা করুন।" : "Something went wrong. Try again.")).slice(0, 240);
  }
  function group(jobs, now) {
    const today = istDay(new Date(now).toISOString());
    const by = (s) => jobs.filter(j => j.status === s);
    const newest = (a, b) => (ms(b.created_at) || 0) - (ms(a.created_at) || 0);
    const running = by("running").sort(newest), queued = by("queued").sort(newest);
    const recent = jobs.filter(j => j.status === "done" || j.status === "failed").sort((a, b) => (ms(b.finished_at || b.created_at) || 0) - (ms(a.finished_at || a.created_at) || 0));
    const doneToday = recent.filter(j => j.status === "done" && istDay(j.finished_at) === today);
    const failed = recent.filter(j => j.status === "failed");
    let minutes = 0; jobs.forEach(j => { if (j.finished_at && istDay(j.finished_at) === today) minutes += minutesBetween(j.started_at, j.finished_at) || 0; });
    return { running, queued, recent, doneToday, failed, minutes };
  }
  const stateChip = (s, lang) => `<span class="status ${s === "done" ? "st-ok" : s === "failed" ? "st-bad" : "st-warn"}">${esc(T(lang, { done: "jsDone", failed: "jsFailed", running: "jsRunning", queued: "jsQueued" }[s] || "jsQueued"))}</span>`;
  const askedBy = (j, lang) => T(lang, { owner: "jByOwner", father: "jByFather", system: "jBySystem" }[j.asked_by] || "jBySystem");
  const tile = (k, v, s, cls = "") => `<div class="tile ${cls}"><span class="k">${esc(k)}</span><span class="v num">${esc(v)}</span>${s ? `<span class="s">${esc(s)}</span>` : ""}</div>`;

  function steps(lines, lang) {
    const ls = (lines || []).slice().sort((a, b) => a.seq - b.seq);
    if (!ls.length) return "";
    return `<ol class="jn-steps" aria-label="${esc(T(lang, "jSteps"))}">${ls.map(l => `<li data-state="${esc(l.state)}">${esc(lang === "bn" && l.text_bn ? l.text_bn : l.text)}</li>`).join("")}</ol>`;
  }
  function card(j, lines, now, lang) {
    const mins = minutesBetween(j.started_at || j.created_at, new Date(now).toISOString());
    const when = j.status === "queued" ? T(lang, "jQueued") : `${T(lang, "jStarted")} ${ago(j.started_at || j.created_at, now, lang)}`;
    return `<article class="jn-card" data-job="${esc(j.id)}" data-status="${esc(j.status)}"><div class="jn-top"><h3>${esc(kindName(j, lang))}</h3>${stateChip(j.status, lang)}</div>
      ${steps(lines, lang)}<p class="muted jn-meta">${esc(when)} · ${esc(T(lang, "jAskedBy"))} ${esc(askedBy(j, lang))}${mins != null && j.status === "running" ? "" : ""}</p></article>`;
  }
  function row(j, now, lang, person) {
    const took = minutesBetween(j.started_at, j.finished_at);
    const body = j.status === "failed" ? `<div class="jn-why"><span class="muted">${esc(failWords(j, lang))}</span>${person === "owner" ? `<button type="button" class="btn t jn-rerun" data-jn-rerun="${esc(j.id)}"><span class="ms">refresh</span>${esc(T(lang, "jRerun"))}</button>` : ""}</div>`
      : j.result ? `<div class="muted">${esc(j.result)}</div>` : "";
    return `<tr class="${j.status === "failed" ? "jn-bad" : ""}" data-job="${esc(j.id)}"><td><b>${esc(kindName(j, lang))}</b>${body}</td>
      <td class="h1">${esc(T(lang, "jAskedBy"))} ${esc(askedBy(j, lang))}</td><td class="num">${esc(ago(j.finished_at || j.created_at, now, lang))}</td>
      <td class="num h1">${took == null ? esc(T(lang, "jDash")) : `${took} ${esc(T(lang, "jMinS"))}`}</td><td>${stateChip(j.status, lang)}</td></tr>`;
  }
  function budgetCard(b, minutes, lang) {
    if (!b) return "";
    const pct = Math.min(100, Math.round(b.writes / b.stop_at * 100)), warn = Math.round(b.warn_at / b.stop_at * 100);
    const cls = b.status === "stopped" ? "bad" : b.status === "warn" ? "warn" : "ok";
    const nf = n => Number(n).toLocaleString("en-IN");
    return `<section class="jn-budget"><div class="jn-bt"><h3>${esc(T(lang, "jBudget"))}</h3><span class="status ${cls === "ok" ? "st-ok" : cls === "warn" ? "st-warn" : "st-bad"}">${esc(T(lang, { ok: "jbOk", warn: "jbWarn", stopped: "jbStopped" }[b.status] || "jbOk"))}</span></div>
      <p class="muted">${esc(T(lang, "jBudgetP"))}</p><div class="frt jn-meter" role="img" aria-label="${esc(T(lang, "jBudgetOf", nf(b.writes), nf(b.stop_at)))}"><i class="${cls}" style="width:${pct}%"></i><u style="left:${warn}%"></u></div>
      <p class="num jn-big">${esc(T(lang, "jBudgetOf", nf(b.writes), nf(b.stop_at)))}</p></section>`;
  }
  function page(st, lang, now, person) {
    lang = lang === "bn" ? "bn" : "en"; now = now || Date.now();
    const head = `<header class="page-h"><h1 class="disp">${esc(T(lang, "jobsT"))}</h1><p>${esc(T(lang, "jobsP"))}</p></header>`;
    if (st.denied) return `<div class="pagewrap jn">${head}<p class="muted">${esc(T(lang, "jOnlyOwner"))}</p></div>`;
    if (!st.jobs) return `<div class="pagewrap jn">${head}<p class="muted">${esc(T(lang, st.offline ? "jOffline" : "jLoading"))}</p></div>`;
    const g = group(st.jobs, now), lines = st.lines || {};
    const tiles = `<div class="tiles jn-tiles">${tile(T(lang, "jRunning"), g.running.length, "")}${tile(T(lang, "jWaiting"), g.queued.length, "")}${tile(T(lang, "jDone"), g.doneToday.length, "")}${tile(T(lang, "jFailed"), g.failed.length, "", g.failed.length ? "bad" : "")}${st.budget ? tile(T(lang, "jMinutes"), T(lang, "jMinutesV", g.minutes), T(lang, "jMinutesP")) : ""}</div>`;
    const active = [...g.running, ...g.queued];
    const sec = (title, n) => `<div class="secttl"><h2>${esc(T(lang, title))}</h2><span class="n num">${n}</span></div>`;
    return `<div class="pagewrap jn">${head}${tiles}
      <div class="jn-cols"><div>${sec("jActive", active.length)}${active.length ? `<div class="jn-cards">${active.map(j => card(j, lines[j.id], now, lang)).join("")}</div>` : `<p class="muted">${esc(T(lang, "jNoneRun"))}</p>`}</div>${budgetCard(st.budget, g.minutes, lang)}</div>
      ${sec("jRecent", g.recent.length)}${g.recent.length ? `<div class="jn-tw"><table class="grid"><thead><tr><th>${esc(T(lang, "jJob"))}</th><th class="h1">${esc(T(lang, "jAskedBy"))}</th><th>${esc(T(lang, "jWhen"))}</th><th class="h1">${esc(T(lang, "jTook"))}</th><th>${esc(T(lang, "jState"))}</th></tr></thead><tbody>${g.recent.slice(0, 40).map(j => row(j, now, lang, person)).join("")}</tbody></table></div>` : `<p class="muted">${esc(T(lang, st.jobs.length ? "jNoneRun" : "jNoneAll"))}</p>`}</div>`;
  }

  // ---- fetching: state lives here so app.js stays small
  const state = { jobs: null, lines: {}, budget: null, denied: false, offline: false, timer: null };
  async function load(F, done) {
    const j = async u => { const r = await F(u); if (r.status === 403) { const e = new Error("denied"); e.denied = true; throw e; } if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); };
    try {
      const [l, b] = await Promise.all([j("/api/v2/jobs?limit=100"), j("/api/v2/budget").catch(() => null)]);
      state.jobs = l.jobs || []; state.budget = b; state.denied = false; state.offline = false;
      const live = state.jobs.filter(x => x.status === "running" || x.status === "queued");
      await Promise.all(live.map(async x => { try { state.lines[x.id] = (await j("/api/v2/jobs/" + encodeURIComponent(x.id))).lines || []; } catch (e) { /* keep older lines */ } }));
    } catch (e) { if (e.denied) state.denied = true; else state.offline = true; }
    done();
  }
  async function rerun(F, id, done) {
    try { await F("/api/v2/jobs/" + encodeURIComponent(id) + "/rerun", { method: "POST" }); } catch (e) { /* the next load shows the truth */ }
    return load(F, done);
  }
  const API = { KINDS, words, kindName, group, failWords, page, state, load, rerun, minutesBetween };
  root.SPJobs = API;
})(typeof window !== "undefined" ? window : globalThis);
