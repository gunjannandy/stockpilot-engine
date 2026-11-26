// AUDIT: serves a built site the way Cloudflare Pages does, with the REAL Pages Functions (web/functions, the real _middleware.js
// with a signed session cookie) over a local D1 that holds the real migrations. Nothing in /api is mocked.
// Run it through vite-node (the handlers import schemas/live-contract.json): npx vite-node tests/e2e-audit.mjs <site dir>
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { localD1 } from "../test/d1.js";
import { signSession } from "../lib/auth.js";
import { FakeKV } from "../test/fakes.mjs";
import ingestWorker from "../ingest/worker.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const FUNCTIONS = path.join(here, "..", "functions");
const types = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".json": "application/json", ".svg": "image/svg+xml" };

export const COOKIE_KEY = "audit-cookie-key-0123456789-abcdefghij";
export const INGEST_KEY = "audit-ingest-key-0123456789";
export const PEOPLE = { owner: "owner@example.test", father: "father@example.test" };

// functions/api/v2/jobs/[id]/rerun.js -> /api/v2/jobs/:id/rerun ; index.js is the folder's own route
function routes() {
  const out = [];
  (function walk(dir, parts) {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      if (e.isDirectory()) { walk(path.join(dir, e.name), [...parts, e.name]); continue; }
      if (!e.name.endsWith(".js") || e.name.startsWith("_")) continue;
      const stem = e.name.slice(0, -3), segs = stem === "index" ? parts : [...parts, stem];
      out.push({ file: path.join(dir, e.name), segs });
    }
  })(FUNCTIONS, []);
  return out;
}
const match = (segs, url) => {
  const have = url.split("/").filter(Boolean);
  if (have.length !== segs.length) return null;
  const params = {};
  for (let i = 0; i < segs.length; i++) {
    const m = /^\[(.+)\]$/.exec(segs[i]);
    if (m) params[m[1]] = have[i]; else if (segs[i] !== have[i]) return null;
  }
  return params;
};

export async function startSite({ siteDir, overlay = [], db = localD1(), now = null, workerKey = "" } = {}) {
  const env = { DB: db, SP: new FakeKV(), SP_PEOPLE: JSON.stringify(PEOPLE), SP_COOKIE_KEY: COOKIE_KEY, SP_INGEST_KEY: INGEST_KEY, SP_OWNER: "owner" };
  const table = [];
  for (const r of routes()) table.push({ ...r, mod: await import(pathToFileURL(r.file).href) });
  const { onRequest: middleware } = await import(pathToFileURL(path.join(FUNCTIONS, "_middleware.js")).href);
  const cookies = { owner: await signSession("owner", COOKIE_KEY), father: await signSession("father", COOKIE_KEY) };
  const seen = [];
  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, "http://x");
    const chunks = []; for await (const c of req) chunks.push(c);
    const body = Buffer.concat(chunks);
    const send = (status, headers, data) => { res.writeHead(status, headers); res.end(data); };
    if (url.pathname === "/__worker/ingest") {   // the separate write-only ingest Worker public jobs post to (web/ingest/worker.js), unchanged
      const ts = Number(req.headers["x-sp-timestamp"]);
      const r = await ingestWorker.fetch(new Request("http://worker.test/", { method: "POST", headers: req.headers, body }), { DB: db, INGEST_KEY: workerKey }, { now: Number.isFinite(ts) ? ts : Date.now() });
      return send(r.status, Object.fromEntries(r.headers), Buffer.from(await r.arrayBuffer()));
    }
    if (url.pathname.startsWith("/api/")) {
      const hit = table.map(t => ({ t, params: match(t.segs, url.pathname.slice(1)) })).find(x => x.params);
      seen.push(`${req.method} ${url.pathname}`);
      if (!hit) return send(404, { "content-type": "application/json" }, '{"error":"no_route"}');
      const fn = hit.t.mod["onRequest" + req.method[0] + req.method.slice(1).toLowerCase()] || hit.t.mod.onRequest;
      if (!fn) return send(405, {}, "");
      const request = new Request("http://127.0.0.1:" + server.address().port + req.url, { method: req.method, headers: req.headers, ...(["GET", "HEAD"].includes(req.method) ? {} : { body }) });
      const ctx = { request, env, data: {}, params: hit.params, now: now?.() ?? undefined, waitUntil() {}, next: async () => fn({ ...ctx }) };
      try {
        const r = await middleware(ctx);
        return send(r.status, Object.fromEntries(r.headers), Buffer.from(await r.arrayBuffer()));
      } catch (e) { return send(500, { "content-type": "application/json" }, JSON.stringify({ error: String(e) })); }
    }
    for (const root of [...overlay, siteDir]) {
      const file = path.join(root, url.pathname === "/" ? "index.html" : decodeURIComponent(url.pathname));
      if (file.startsWith(path.resolve(root)) && fs.existsSync(file) && fs.statSync(file).isFile())
        return send(200, { "content-type": types[path.extname(file)] || "application/octet-stream", "cache-control": "no-store" }, fs.readFileSync(file));
    }
    send(404, { "content-type": "text/plain" }, "no");
  });
  await new Promise(r => server.listen(0, "127.0.0.1", r));
  return { base: `http://127.0.0.1:${server.address().port}`, db, env, cookies, seen, close: () => new Promise(r => server.close(r)) };
}
