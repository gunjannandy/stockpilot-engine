// T25: drives the real "Every stock" screen on a generated 9,000-stock file (neutral names), checks filters combine and
// persist across a reload, and takes screenshots at 1440, 1100 and 400 wide in light and dark.
// Usage: node web/tests/universe-shots.mjs <out dir>
import http from "node:http"; import fs from "node:fs"; import path from "node:path"; import { createRequire } from "node:module";
const require = createRequire(import.meta.url); const { chromium } = require("playwright");
const out = process.argv[2] || "docs/status/shots-t25"; fs.mkdirSync(out, { recursive: true });
const root = new URL("../public/", import.meta.url).pathname;
const N = 9000, W = ["Alpha", "Bharat", "Coastal", "Delta", "Eastern", "Fortune", "Global", "Indo", "Jupiter", "Kaveri"], X = ["Industries", "Textiles", "Pharma", "Steel", "Foods", "Power"], SEC = ["Banks", "Pharma", "IT services", "Metals", "Autos", "Power", "Textiles", "Food"];
const t = { built_at: "2026-11-25T10:00:00+05:30", n: N, symbol: [], exchange: [], segment: [], name: [], sector: [], pe: [], growth: [], chance_6m: [], mcap_cr: [], last: [], day_change_pct: [] };
for (let i = 0; i < N; i++) { t.symbol.push(W[i % 10].slice(0, 4).toUpperCase() + X[i % 6].slice(0, 3).toUpperCase() + i); t.exchange.push(i % 3 ? "NSE" : "BSE"); t.segment.push(i % 3 ? (i % 7 ? "NSE" : "NSE_SME") : "BSE");
  t.name.push(`${W[i % 10]} ${X[i % 6]} ${i} Limited`); t.sector.push(i % 5 === 0 ? null : SEC[i % 8]); t.pe.push(i % 6 === 0 ? null : +(5 + ((i * 7 + (i >> 3) * 5) % 60) + .3).toFixed(1)); t.growth.push(i % 8 === 0 ? null : ((i * 3 + (i >> 4)) % 50) - 12);
  t.chance_6m.push(i % 4 === 0 ? null : +(0.3 + ((i * 11 + (i >> 2)) % 50) / 100).toFixed(2)); t.mcap_cr.push(i % 9 === 0 ? null : 100 * (1 + ((i * 13 + (i >> 5) * 7) % 400)) * (i % 50 === 0 ? 40 : 1)); t.last.push(+(10 + i * .73).toFixed(2)); t.day_change_pct.push(0); }
const body = JSON.stringify(t); const types = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".json": "application/json" };
const server = http.createServer((req, res) => { const u = new URL(req.url, "http://x");
  if (u.pathname === "/screen/universe.json") { res.setHeader("content-type", "application/json"); return res.end(body); }
  if (u.pathname === "/api/me") return res.end(JSON.stringify({ person: "father" }));
  const f = path.join(root, u.pathname === "/" ? "index.html" : decodeURIComponent(u.pathname)); if (!fs.existsSync(f) || fs.statSync(f).isDirectory()) { res.statusCode = 404; return res.end("no"); }
  res.setHeader("content-type", types[path.extname(f)] || "application/octet-stream"); res.end(fs.readFileSync(f)); });
await new Promise(r => server.listen(0, r)); const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ args: ["--no-sandbox"] }); let bad = 0;
const ok = (c, m) => { console.log((c ? "ok   " : "FAIL ") + m); if (!c) bad++; };
const count = p => p.$eval(".uct b", e => +e.textContent.replace(/,/g, ""));
for (const theme of ["light", "dark"]) for (const [label, width] of [["1440", 1440], ["1100", 1100], ["400", 400]]) {
  const ctx = await browser.newContext({ viewport: { width, height: 900 }, deviceScaleFactor: 1, colorScheme: theme });
  await ctx.route(/^https?:\/\/(?!127\.0\.0\.1)/, r => r.abort());
  const page = await ctx.newPage(); const errs = []; page.on("pageerror", e => errs.push(e.message));
  await page.goto(base + "/#universe"); await page.waitForSelector(".ug tbody tr", { timeout: 15000 });
  const all = await count(page); const first = theme === "light" && label === "1440";
  if (first) {
    ok(all === N, `loads the full universe (${all} rows counted)`);
    await page.click('[data-uf="pe:lt15"]'); const a = await count(page);
    await page.click('[data-uf="exchange:NSE"]'); const ab = await count(page);
    ok(a < all && ab < a, `filters combine (${all} -> ${a} -> ${ab})`);
    await page.reload(); await page.waitForSelector(".ug tbody tr");
    ok(await count(page) === ab && await page.$eval('[data-uf="pe:lt15"]', e => e.getAttribute("aria-pressed")) === "true", "filters persist after a reload");
    await page.click('th [data-us="pe"]'); const pes = await page.$$eval(".ug tbody tr td:nth-child(3)", c => c.slice(0, 50).map(x => parseFloat(x.textContent)));
    ok(pes.every((v, i) => !i || pes[i] <= pes[i - 1]), "sorting by P/E orders the rows");
    await page.click("[data-uclear]"); ok(await count(page) === N, "Clear filters restores all");
    await page.click('[data-uf="pe:lt15"]'); await page.click('[data-uf="size:small"]');
  } else await page.evaluate(() => 0);
  if (!first) { await page.evaluate(() => localStorage.setItem("sp.universe.v1", JSON.stringify({ filters: { pe: "lt15", size: "small" }, sort: null }))); await page.reload(); await page.waitForSelector(".ug tbody tr"); }
  const noScroll = await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1);
  if (!noScroll) console.log(await page.evaluate(() => [...document.querySelectorAll("body *")].filter(e => e.getBoundingClientRect().right > innerWidth + 1).slice(0, 6).map(e => e.tagName + "." + e.className + " " + Math.round(e.getBoundingClientRect().right)).join(" | ")));
  ok(noScroll, `${theme} ${label}: no sideways scroll`);
  await page.screenshot({ path: path.join(out, `universe-${label}-${theme}.png`) });
  ok(!errs.length, `${theme} ${label}: no page errors ${errs[0] || ""}`);
  await ctx.close();
}
await browser.close(); server.close(); process.exit(bad ? 1 : 0);
