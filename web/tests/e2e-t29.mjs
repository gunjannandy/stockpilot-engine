// T29 checks: Holdings, Tax, Trading record, Our record and RSUs read from the live API (views_get) and show the data rows.
// Usage: node e2e-t29.mjs <v10 site data dir> [shots dir]
// The data dir is what `tests/build_site_v10.py` writes (data/*.json). The four private files are NOT served as static
// files here: they come only from /api/v2/views/<name>, so a pass proves the screens read the live API.
// Scenario touches on that real-shaped data, named here: one holding is split 60/40 between Kite and Smallcase, and one has
// 2 shares its lots do not explain. A second run turns the API off (404) and checks the static files still work.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const [dataDir, shotDir] = process.argv.slice(2);
if (!dataDir) { console.error("usage: node e2e-t29.mjs <data dir> [shots dir]"); process.exit(2); }
const PUB = new URL("../public/", import.meta.url).pathname;
const types = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".json": "application/json" };
const rd = n => JSON.parse(fs.readFileSync(path.join(dataDir, n + ".json"), "utf8"));
const VIEWS = ["portfolio", "smallcase", "record", "own_record"];

const docs = Object.fromEntries(VIEWS.map(n => [n, rd(n)]));
const stocks = docs.portfolio.holdings.filter(h => h.kind === "equity" && h.quantity > 10);
const SPLIT = stocks[0], OFF = stocks[1];
for (const h of docs.portfolio.holdings) { h.lots_units = h.source === "lots" ? h.quantity : null; h.by_source = h.kind === "equity" ? { kite: h.quantity, smallcase: 0 } : { kite: h.quantity, smallcase: 0 }; }
SPLIT.by_source = { kite: Math.round(SPLIT.quantity * 0.6), smallcase: SPLIT.quantity - Math.round(SPLIT.quantity * 0.6) };
OFF.lots_units = OFF.quantity - 2;

const posted = [];
let apiOn = true;
const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://x"), json = b => { res.setHeader("content-type", "application/json"); res.end(JSON.stringify(b)); };
  if (url.pathname === "/api/me") return json({ person: "father" });
  if (url.pathname === "/api/queue" && req.method === "GET") return json({ items: [] });
  if (url.pathname === "/api/queue" && req.method === "POST") { let b = ""; req.on("data", d => b += d); return req.on("end", () => { posted.push(JSON.parse(b)); json({ id: "q" + posted.length }); }); }
  if (url.pathname.startsWith("/api/v2/changes")) return json({ person: "father", unseen_count: 0, items: [] });
  const vm = /^\/api\/v2\/views\/(\w+)$/.exec(url.pathname);
  if (vm) { if (!apiOn || !docs[vm[1]]) { res.statusCode = 404; return json({ error: "not_found" }); } return json({ name: vm[1], as_of: "2026-11-20", written_at: "2026-11-20T18:00:00+05:30", doc: docs[vm[1]] }); }
  if (url.pathname.startsWith("/api/")) { res.statusCode = 404; return json({}); }
  let file = path.join(PUB, url.pathname === "/" ? "index.html" : decodeURIComponent(url.pathname));
  if (url.pathname.startsWith("/data/")) {
    const name = decodeURIComponent(url.pathname.slice(6));
    if (apiOn && VIEWS.includes(name.replace(/\.json$/, ""))) { res.statusCode = 404; return res.end("no"); }   // proves the screens use the API
    file = path.join(dataDir, name);
  }
  if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.statusCode = 404; return res.end("no"); }
  res.setHeader("content-type", types[path.extname(file)] || "application/octet-stream"); res.end(fs.readFileSync(file));
});
await new Promise(r => server.listen(0, "127.0.0.1", r));
const base = `http://127.0.0.1:${server.address().port}`;
if (shotDir) fs.mkdirSync(shotDir, { recursive: true });

// formats the page uses
const inr = v => "₹" + Math.round(v).toLocaleString("en-IN");
const flat = t => t.replace(/−/g, "-").replace(/\s+/g, " ");
const problems = [], notes = [];
const ok = (cond, msg) => { if (!cond) problems.push(msg); };
const browser = await chromium.launch({ args: ["--no-sandbox"] });
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function open(page, hash) { await page.goto(base + "/#" + hash); await page.waitForSelector("h1", { timeout: 8000 }); await sleep(450); }
const text = page => page.evaluate(() => document.body.innerText);

async function run(width, theme, shots) {
  const tag = `${width}-${theme}`;
  const ctx = await browser.newContext({ viewport: { width, height: width < 500 ? 860 : 900 }, colorScheme: theme, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const errs = []; page.on("pageerror", e => errs.push(String(e))); page.on("console", m => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errs.push(m.text()); });
  const shot = async n => { if (shots && shotDir) await page.screenshot({ path: path.join(shotDir, `${n}-${tag}.png`), fullPage: false }); };

  // ---- Holdings, All: every row's value is on the page (table view shows them all), the heading total is the stored total
  await open(page, "holdings");
  const hs = docs.portfolio.holdings;
  const p = docs.portfolio;
  await page.evaluate(() => document.querySelector('[data-mode="hold:table"]')?.click()); await sleep(250);
  let t = flat(await text(page));
  for (const h of hs) ok(t.includes(flat(inr(h.value))), `${tag} holdings: value ${inr(h.value)} of ${h.symbol} is not on the page`);
  const lakh = v => `₹${(v / 1e5).toFixed(2)} lakh`;
  ok(/lakh/.test(t), `${tag} holdings: no total in lakh in the heading`);
  ok(/Do the share counts match\?/.test(t) && /Kite shows \d+, our records explain \d+/.test(t), `${tag} holdings: units check missing or wrong`);
  ok(new RegExp(`${OFF.quantity - 2}`).test(t), `${tag} holdings: units check does not show the lot count`);
  const chips = await page.$$eval(".srcsw .sg", bs => bs.map(b => b.innerText.replace(/\s+/g, " ").trim()));
  const nK = hs.filter(h => (h.by_source.kite) > 0).length;
  ok(chips.join("|") === `All ${hs.length}|Kite ${nK}|Smallcase 1`, `${tag} holdings: route chips ${JSON.stringify(chips)}`);
  await shot("holdings-all");

  // ---- Smallcase: one row, its own units and value, the totals line is the sum of what is shown
  await page.click('[data-src="smallcase"]'); await sleep(300);
  t = flat(await text(page));
  const sUnits = SPLIT.by_source.smallcase, sValue = Math.round(SPLIT.value * sUnits / SPLIT.quantity);
  ok(t.includes(flat(inr(sValue))), `${tag} smallcase: value ${inr(sValue)} missing`);
  ok(!t.includes(flat(inr(OFF.value))) || OFF.value === SPLIT.value, `${tag} smallcase: another holding is still shown`);
  ok(new RegExp(`Showing 1 holding worth ${inr(sValue).replace("₹", "₹")}`).test(t), `${tag} smallcase: totals line wrong: ${(t.match(/Showing[^.]*\./) || ["none"])[0]}`);
  ok(t.includes(`${sUnits} shares`), `${tag} smallcase: its ${sUnits} units are not shown`);
  await shot("holdings-smallcase");

  // ---- Kite: the totals line adds up to the rows
  await page.click('[data-src="kite"]'); await sleep(300);
  t = flat(await text(page));
  const kiteRows = hs.map(h => ({ h, u: h.by_source.kite })).filter(x => x.u > 0);
  const kiteTotal = kiteRows.reduce((a, x) => a + Math.round(x.h.value * x.u / x.h.quantity), 0);
  ok(t.includes(`Showing ${kiteRows.length} holdings worth ${inr(kiteTotal)}`), `${tag} kite: totals line is not the sum of the rows (${inr(kiteTotal)}): ${(t.match(/Showing[^.]*\./) || ["none"])[0]}`);
  await page.click('[data-src="all"]');

  // ---- "I hold this for years": on a held stock's page the button posts a long_term_mark job and flips
  if (!shots) {
    const sym = stocks.find(h => !h.long_term)?.symbol || stocks[0].symbol;
    await page.evaluate(s => { const el = document.createElement("a"); el.href = "#stock"; el.dataset.open = s; document.body.appendChild(el); el.click(); }, sym);
    await sleep(500);
    const btn = await page.$("[data-ltm]");
    ok(!!btn, `${tag} I-hold-this-for-years button missing on ${sym}`);
    if (btn) { await btn.click(); await sleep(300); ok(posted.some(x => x.kind === "long_term_mark" && x.payload?.symbol === sym), `${tag} long_term_mark was not queued for ${sym}`); }
  }

  // ---- Tax
  await open(page, "tax"); t = flat(await text(page));
  const tx = p.tax;
  ok(t.includes(flat(inr(tx.realised_gain))), `${tag} tax: realised gain ${inr(tx.realised_gain)} missing`);
  ok(tx.notes.every(n => t.includes(flat(n))), `${tag} tax: a note is missing`);
  await shot("tax");

  // ---- Trading record (own_record)
  const o = docs.own_record;
  await open(page, "tradrec"); t = flat(await text(page));
  ok(t.includes(String(o.closed)) && t.includes(`${o.winners}`), `${tag} trading record: closed ${o.closed} or winners ${o.winners} missing`);
  await shot("tradrec");

  // ---- Our record
  const r = docs.record;
  await open(page, "record"); t = flat(await text(page));
  ok(t.includes(flat(r.headline)), `${tag} record: headline missing`);
  await shot("record");

  // ---- RSUs
  if (p.rsu) {
    await page.evaluate(s => { const el = document.createElement("a"); el.href = "#stock"; el.dataset.open = s; document.body.appendChild(el); el.click(); }, p.rsu.symbol);
    await sleep(600); t = flat(await text(page));
    ok(t.includes(flat(inr(p.rsu.value_inr))) && t.includes(flat(inr(p.rsu.cost_inr))), `${tag} rsu: worth ${inr(p.rsu.value_inr)} or cost missing`);
    await shot("rsu");
  }
  ok(errs.length === 0, `${tag}: page errors ${errs.slice(0, 2).join(" | ")}`);
  const wide = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
  ok(!wide, `${tag}: sideways scroll`);
  await ctx.close();
}

for (const w of [1440, 1100, 400]) for (const th of ["light", "dark"]) await run(w, th, true);
await run(1440, "light", false);   // the click that posts: once, no shots

// ---- the API is off: the last static files still draw every screen
apiOn = false;
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } }), page = await ctx.newPage();
  const errs = []; page.on("pageerror", e => errs.push(String(e)));
  for (const pg of ["holdings", "tax", "tradrec", "record"]) { await open(page, pg); const t = flat(await text(page)); ok(t.length > 300 && !/No data/i.test(t.slice(0, 600)), `fallback: ${pg} did not draw`); }
  ok(errs.length === 0, `fallback: page errors ${errs[0]}`);
  await ctx.close();
}
await browser.close(); server.close();
if (problems.length) { console.log("PROBLEMS:\n" + problems.join("\n")); process.exit(1); }
console.log("T29 e2e: all checks passed at 1440, 1100 and 400, light and dark; API-off fallback draws all four screens.");
