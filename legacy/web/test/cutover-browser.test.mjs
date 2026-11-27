// V4PREP: the hard-block checker against a real browser, a local gate and a built fixture site.
// Runs only when SP_CUTOVER_SITE points at a built site (python tests/build_site_v10.py <dir>) and Playwright is installed.
//   SP_CUTOVER_SITE=/tmp/site node --test web/test/cutover-browser.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { createRequire } from "node:module";
import { checkUrl, mintCookie } from "../../scripts/cutover/check.mjs";
import { verifySession } from "../lib/auth.js";

const site = process.env.SP_CUTOVER_SITE;
const have = (() => { try { createRequire(import.meta.url)("playwright"); return !!site && fs.existsSync(path.join(site, "index.html")); } catch { return false; } })();
const KEY = "k".repeat(40);
const types = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".json": "application/json" };

// Serves `dir` behind a gate like the real one: no valid session cookie means 302 to /login.
function serve(dir) {
  const server = http.createServer(async (req, res) => {
    if (new URL(req.url, "http://x").pathname === "/login") { res.setHeader("content-type", "text/html"); return res.end("<h1>Sign in</h1>"); }
    const cookie = /sp_session=([^;]+)/.exec(req.headers.cookie || "")?.[1];
    if (!(await verifySession(cookie, KEY))) { res.statusCode = 302; res.setHeader("Location", "/login"); return res.end(); }
    const p = new URL(req.url, "http://x").pathname;
    if (p === "/api/me") return res.end(JSON.stringify({ person: "Owner" }));
    if (p.startsWith("/api/")) { res.statusCode = 200; res.setHeader("content-type", "application/json"); return res.end("{}"); }
    const f = path.join(dir, p === "/" ? "index.html" : decodeURIComponent(p));
    if (!f.startsWith(path.resolve(dir)) || !fs.existsSync(f)) { res.statusCode = 404; return res.end("no"); }
    res.setHeader("content-type", types[path.extname(f)] || "application/octet-stream"); res.end(fs.readFileSync(f));
  });
  return new Promise((r) => server.listen(0, "127.0.0.1", () => r({ server, url: `http://127.0.0.1:${server.address().port}/` })));
}

const copy = (mutate) => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), "cutover-"));
  fs.cpSync(site, d, { recursive: true });
  mutate(d);
  return d;
};

test("good site passes all four; broken JS, changed number and a rejected cookie each fail the right block", { skip: !have, timeout: 240000 }, async () => {
  const cookie = await mintCookie({ SP_COOKIE_KEY: KEY }, "owner");

  const good = await serve(site);
  const ok = await checkUrl(good.url, { cookie });
  assert.deepEqual(ok.failed, [], JSON.stringify(ok.detail));
  assert.ok(ok.detail.rows > 0);
  const noCookie = await checkUrl(good.url, {});
  assert.deepEqual(noCookie.failed, ["page_loads"], "a closed gate is a failed load, not a pass");
  const wrong = await checkUrl(good.url, { cookie: await mintCookie({ SP_COOKIE_KEY: "z".repeat(40) }, "owner") });
  assert.ok(wrong.failed.includes("page_loads") && wrong.detail.gate, JSON.stringify(wrong));
  good.server.close();

  const brokenDir = copy((d) => fs.writeFileSync(path.join(d, "app.js"), `throw new Error("boom");\n` + fs.readFileSync(path.join(d, "app.js"), "utf8")));
  const b = await serve(brokenDir);
  const bad = await checkUrl(b.url, { cookie });
  assert.ok(bad.failed.includes("js_page_error"), JSON.stringify(bad));
  b.server.close();

  // The data says one price; change the data file the page reads and the screen no longer matches the file the check re-reads?
  // Both read the same file, so change what the screen shows instead: the page's price formatter.
  const numDir = copy((d) => {
    const js = path.join(d, "app.js");
    fs.writeFileSync(js, fs.readFileSync(js, "utf8").replace('const pct = (v, d = 0) => v == null ? "–" : (v * 100).toFixed(d) + "%";', 'const pct = (v, d = 0) => v == null ? "–" : (v * 100 + 1).toFixed(d) + "%";'));
  });
  const n = await serve(numDir);
  const wrongNum = await checkUrl(n.url, { cookie });
  assert.ok(wrongNum.failed.includes("numbers_match"), JSON.stringify(wrongNum));
  n.server.close();
});
