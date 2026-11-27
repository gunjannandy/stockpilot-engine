// V2: after the Kite login the page follows the Sync job: "Checking login, logged in, saving holdings, done, 3 changes".
// Plain script (browser) that also loads in Node for tests. `follow` is pure over an injected fetch and clock.
(function (root) {
  "use strict";
  const POLL_MS = 2000, GIVE_UP_MS = 5 * 60000;
  const words = {
    en: { title: "Syncing from Zerodha", waiting: "Waiting for the VM to pick it up (about a minute)", slow: "This is taking longer than usual. It keeps running; check the Jobs page.", close: "Close" },
    bn: { title: "Zerodha থেকে Sync হচ্ছে", waiting: "প্রায় এক মিনিটের মধ্যে শুরু হবে", slow: "আজ একটু দেরি হচ্ছে। কাজ চলছে; Jobs পাতায় দেখুন।", close: "বন্ধ করুন" },
  };
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function html(state, lang) {
    const t = words[lang] || words.en;
    const lines = (state.lines || []).slice().sort((a, b) => a.seq - b.seq).map(l => `<li data-state="${esc(l.state)}">${esc(lang === "bn" && l.text_bn ? l.text_bn : l.text)}</li>`).join("");
    const job = state.job;
    let tail = "";
    if (!job || job.status === "queued") tail = `<p class="sync-wait">${esc(t.waiting)}</p>`;
    else if (job.status === "failed") tail = `<p class="job-err">${esc(lang === "bn" && job.error_bn ? job.error_bn : job.error || "")}</p>`;
    else if (job.status === "done") tail = `<p class="job-ok">${esc(job.result || "")}</p>`;
    if (state.slow && (!job || job.status === "queued" || job.status === "running")) tail += `<p class="sync-slow">${esc(t.slow)}</p>`;
    return `<div class="sync-banner" role="status" data-state="${esc(job ? job.status : "queued")}"><strong>${esc(t.title)}</strong><ul>${lines}</ul>${tail}<button type="button" data-close>${esc(t.close)}</button></div>`;
  }

  // Poll until done or failed (or too long). `onState` gets every new state; resolves with the last one.
  async function follow(id, { fetch: F, onState, sleep, now = Date.now, pollMs = POLL_MS }) {
    const t0 = now();
    let last = { job: null, lines: [] };
    for (;;) {
      try { const r = await F("/api/v2/jobs/" + encodeURIComponent(id)); last = { ...r, slow: now() - t0 > GIVE_UP_MS }; } catch (e) { last = { ...last, slow: now() - t0 > GIVE_UP_MS }; }
      onState(last);
      if (last.job && (last.job.status === "done" || last.job.status === "failed")) return last;
      if (now() - t0 > 2 * GIVE_UP_MS) return last;
      await sleep(pollMs);
    }
  }

  function mount(win, doc) {
    const id = new URLSearchParams(win.location.search).get("job");
    if (!id || !win.location.search.includes("synced=1")) return;
    const lang = (doc.documentElement.lang || "en").startsWith("bn") ? "bn" : "en";
    const box = doc.createElement("div");
    box.id = "sync-follow";
    doc.body.prepend(box);
    box.addEventListener("click", e => { if (e.target.closest("[data-close]")) box.remove(); });
    const get = u => win.fetch(u, { credentials: "same-origin" }).then(r => r.json());
    follow(id, { fetch: get, onState: s => { box.innerHTML = html(s, lang); }, sleep: ms => new Promise(r => win.setTimeout(r, ms)) });
  }

  root.SPSync = { html, follow, mount, words };
  if (typeof document !== "undefined" && root.document === document) document.addEventListener("DOMContentLoaded", () => mount(root, document));
})(typeof window !== "undefined" ? window : globalThis);
