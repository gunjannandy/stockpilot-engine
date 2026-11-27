/* QUEUE (#114): the page's buttons as D1 jobs. Behaviour only; app.js draws the toasts.
   Every button kind that used to post to the KV queue now posts a job to /api/v2/jobs, except feedback (its own route)
   and ask_analyst (the `analyse` job). The VM's one-minute check runs the job (src/stockpilot/jobs/buttons.py). */
(function (root) {
  "use strict";
  const JOBS = "/api/v2/jobs";
  const exchangeOf = p => p.exchange || "NSE";
  const SHOW = { queued: "pending", running: "taken", done: "done", failed: "failed" };

  // Where one old queue request goes now: { url, body }.
  function plan(kind, payload) {
    if (kind === "feedback") return { url: "/api/v2/feedback", body: { text: payload.text } };
    if (kind === "ask_analyst") return { url: JOBS, body: { kind: "analyse", payload: { symbol: payload.symbol, exchange: exchangeOf(payload) } } };
    return { url: JOBS, body: { kind, payload: payload || {} } };
  }

  // Post it. { ok: true, id } or { ok: false, status }.
  async function send(fetchFn, kind, payload) {
    const p = plan(kind, payload);
    try {
      const r = await fetchFn(p.url, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(p.body) });
      if (!r.ok) return { ok: false, status: r.status };
      return { ok: true, id: (await r.json()).id };
    } catch (e) { return { ok: false, status: 0 }; }
  }

  // The undo button posts the opposite job. A job cannot be taken back once the VM has it, so only these three have one.
  function inverse(kind, payload) {
    if (kind === "watchlist_add") return { kind: "watchlist_remove", payload };
    if (kind === "watchlist_remove") return { kind: "watchlist_add", payload };
    if (kind === "long_term_mark") return { kind, payload: { ...payload, on: !payload.on } };
    return null;
  }

  // The owner's job list in the shape the Health table and the failed-request notice read (oldest first).
  function items(jobs) {
    return (jobs || []).slice().sort((a, b) => (a.created_at < b.created_at ? -1 : 1)).map(j => ({
      id: j.id, kind: j.kind, payload: j.payload || {}, at: j.created_at, status: SHOW[j.status] || j.status, note: j.error || j.result || "" }));
  }

  root.SPButtons = { plan, send, inverse, items, JOBS };
})(typeof window !== "undefined" ? window : globalThis);
