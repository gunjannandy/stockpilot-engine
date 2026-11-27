// T22: real screenshots of the stock screen (page and list pane) plus a layout-shift and behaviour check.
// Serves web/public with a mock API built from the contract fixtures and invented data. Usage: node shots-t22.mjs <out dir>
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const outDir = process.argv[2] || "shots-t22";
fs.mkdirSync(outDir, { recursive: true });
const pub = path.resolve(new URL("../public", import.meta.url).pathname);
const fx = n => JSON.parse(fs.readFileSync(new URL(`../../tests/fixtures/live/${n}.json`, import.meta.url), "utf8"));
const types = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".json": "application/json" };

// ---- invented history: 1,500 weekday candles ending 2026-11-23, a quiet climb with noise
function history(sym, n, start, seed) {
  let s = seed; const rnd = () => (s = (s * 1664525 + 1013904223) % 4294967296) / 4294967296;
  const dates = []; const d = new Date("2026-11-23T00:00:00Z");
  while (dates.length < n) { if (d.getUTCDay() % 6) dates.unshift(d.toISOString().slice(0, 10)); d.setUTCDate(d.getUTCDate() - 1); }
  let p = start; const open = [], high = [], low = [], close = [], volume = [];
  for (let i = 0; i < n; i++) { const o = p; p = Math.max(5, p * (1 + (rnd() - 0.48) * 0.028 + 0.0004)); const c = p; open.push(+o.toFixed(2)); close.push(+c.toFixed(2)); high.push(+(Math.max(o, c) * (1 + rnd() * 0.01)).toFixed(2)); low.push(+(Math.min(o, c) * (1 - rnd() * 0.01)).toFixed(2)); volume.push(Math.round(80000 + rnd() * 120000)); }
  const ma = k => close.map((_, i) => i < k - 1 ? null : +(close.slice(i - k + 1, i + 1).reduce((a, b) => a + b, 0) / k).toFixed(2));
  return { symbol: sym, exchange: "NSE", listed_on: dates[0], as_of: dates[n - 1], adjusted: true, dates, open, high, low, close, volume, dma50: ma(50), dma200: ma(200) };
}
const A = history("FIXA", 1500, 40, 7), B = history("NOFC", 260, 120, 11);
const last = A.close[A.close.length - 1];
const facts = fx("files/stock_facts"); facts.today.last = last;
const callRow = fx("routes/call_get").response.call;
const scale = last / 103;
for (const k of ["low", "likely", "high"]) for (const h of ["1m", "3m", "6m"]) callRow[`${k}_${h}`] = +(callRow[`${k}_${h}`] * scale).toFixed(1);
callRow.form.what_would_change = [{ level: +(last * 0.92).toFixed(1), text: "A close below this breaks the view" }, { level: +(last * 1.18).toFixed(1), text: "A close above this means take some profit" }];
const mode = { stale: false, nocall: false };
const holding = { symbol: "FIXA", name: "Fixture Alpha Ltd", quantity: 40, value: 40 * last, gain_pct: 0.31, share: 0.12, tax_note: "Held over a year, taxed at the lower rate.", price: last,
  lots: [{ acquired_on: A.dates[1200], quantity: 25, cost: A.close[1200], long_term: true, turns_long_term_on: A.dates[1452] }, { acquired_on: A.dates[1380], quantity: 15, cost: A.close[1380], long_term: false, turns_long_term_on: "2027-03-02" }] };
const D = {
  meta: { as_of: "2026-11-24", calls_on: "2026-11-24", status: { text: "Everything is up to date." } }, today: { as_of: "2026-11-24", buy: [], sell: [], watch_triggers: [], not_yet: [], keep: [], since: { new: [] } },
  calls: { buys: [], sells: [], follow: [] }, market: {}, portfolio: { holdings: [holding] }, watchlist: { rows: [{ symbol: "FIXA", name: "Fixture Alpha Ltd", why: [], close: last }] }, ideas: { ranking: [], near_misses: [] },
  search: [{ symbol: "FIXA", name: "Fixture Alpha Ltd", exchange: "NSE" }, { symbol: "NOFC", name: "Never Forecast Ltd", exchange: "NSE" }], record: { calls: [{ symbol: "FIXA", action: "buy", made_on: A.dates[1300] }, { symbol: "FIXA", action: "hold", made_on: A.dates[1420] }], dates: [] }, own_record: {}, smallcase: {}, health: {}, feedback: { items: [] }, settings: {}, learned: {}, funds: {}, fund_research: {}, indices: {}, flows: {},
  trades_closed: { rows: [{ symbol: "FIXA", sold_on: A.dates[1330], quantity: 10, cost: 1, proceeds: 2, gain: 1, term: "short" }] }, calls_outcomes: { rows: [{ symbol: "FIXA", action: "sell", made_on: A.dates[1100] }] }, lookup: {},
};
const searchIndex = { entries: [{ symbol: "FIXA", name: "Fixture Alpha Ltd", exchange: "NSE" }, { symbol: "NOFC", name: "Never Forecast Ltd", exchange: "NSE" }] };
const reqLog = [];
const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://x"), p = url.pathname, J = o => { res.setHeader("content-type", "application/json"); res.end(JSON.stringify(o)); };
  reqLog.push(req.method + " " + p);
  if (p === "/api/me") return J({ person: "father" });
  if (p === "/api/queue") return J({ items: [] });
  if (p.startsWith("/data/") && !p.startsWith("/data/stock/") && !p.startsWith("/data/history/")) { const k = path.basename(p, ".json"); return J(D[k] ?? {}); }
  if (p === "/search/index.json") return J(searchIndex);
  if (p === "/chart/FIXA.json") return J(A); if (p === "/chart/NOFC.json") return J(B);
  if (p === "/stock/FIXA.json" || p === "/stock/NOFC.json") return J({ ...facts, symbol: p.slice(7, 11), name: p.includes("NOFC") ? "Never Forecast Ltd" : facts.name });
  if (p === "/api/v2/calls/FIXA") { const c = { ...callRow, out_of_date: mode.stale }; return J({ call: c, changes: [] }); }
  if (p.startsWith("/api/v2/calls/")) { res.statusCode = 404; return J({ error: "no call" }); }
  if (p === "/api/v2/quotes") { const s = url.searchParams.get("symbols"); return J({ quotes: [{ symbol: s, exchange: "NSE", price: +(last * 1.004).toFixed(2), prev_close: last, as_of: new Date().toISOString(), source: "yahoo", age_seconds: 95 }] }); }
  if (p === "/api/v2/jobs" && req.method === "POST") { mode.job = { n: 0 }; return J({ id: "job_t22", status: "queued" }); }
  if (p === "/api/v2/jobs/job_t22") { mode.job.n++; const done = mode.job.n >= 2; if (done) mode.stale = false; return J({ job: { id: "job_t22", kind: "analyse", status: done ? "done" : "running", result: done ? "Forecast is ready" : null }, lines: [{ seq: 1, state: "ok", text: "Read the numbers" }, ...(done ? [{ seq: 2, state: "ok", text: "Wrote the forecast" }] : [{ seq: 2, state: "info", text: "Writing the forecast" }])] }); }
  if (p === "/api/v2/changes/seen") return J({ ok: true });
  if (p.startsWith("/api/")) return J({ items: [] });
  const file = path.join(pub, p === "/" ? "index.html" : decodeURIComponent(p));
  if (!file.startsWith(pub) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.statusCode = 404; return res.end("no"); }
  res.setHeader("content-type", types[path.extname(file)] || "application/octet-stream"); res.end(fs.readFileSync(file));
});
await new Promise(r => server.listen(0, r));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ args: ["--no-sandbox"] });
const fails = []; const check = (ok, what) => { if (!ok) { fails.push(what); console.error("FAIL:", what); } else console.log("ok:", what); };
const sizes = [["1440", { width: 1440, height: 900 }], ["1100", { width: 1100, height: 800 }], ["400", { width: 400, height: 860 }]];
async function open(ctx, hash, sym) {
  const page = await ctx.newPage(); const errs = []; page.on("pageerror", e => errs.push(String(e))); page.on("console", m => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errs.push(m.text()); });
  await page.addInitScript(s => { localStorage.setItem("sp-sym", JSON.stringify(s)); }, sym);
  await page.addInitScript(() => { window.__cls = 0; window.__src = []; new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput && !(e.sources || []).every(s => s.node && s.node.parentElement && s.node.parentElement.closest(".sk-cv"))) { window.__cls += e.value;   /* the chart library laying out its own canvas moves no page content, so it is not counted */ window.__src.push(e.value.toFixed(4) + " " + (e.sources || []).map(s => (s.node ? ((s.node.outerHTML.slice(0, 70)) + "<" + (s.node.parentElement?.className || "") + (s.node.id ? "#" + s.node.id : "")).toString().slice(0, 60) + " " + Math.round(s.previousRect.y) + "->" + Math.round(s.currentRect.y) : "")).join(",")); } }).observe({ type: "layout-shift", buffered: true }); });
  await page.goto(base + "/" + hash); page.errs = errs; return page;
}
const ready = async page => { await page.waitForSelector(".sk-cv canvas", { timeout: 8000 }); await page.evaluate(() => document.fonts.ready); await page.waitForTimeout(500); };
for (const scheme of ["light", "dark"]) for (const [label, viewport] of sizes) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: label === "1440" ? 1 : 1, colorScheme: scheme, hasTouch: label === "400" });
  await ctx.route(/^https?:\/\/(?!127\.0\.0\.1)/, r => r.abort());
  mode.stale = scheme === "dark";   // dark shots show the amber out-of-date state
  const page = await open(ctx, "#stock", "FIXA"); await ready(page);
  await page.screenshot({ path: path.join(outDir, `stock-${label}-${scheme}.png`), fullPage: true });
  await page.evaluate(() => scrollTo(0, 0));
  const cls = await page.evaluate(() => window.__cls);
  check(cls < 0.02, `${label} ${scheme}: layout shift on load ${cls.toFixed(4)} (< 0.02) ${cls >= 0.02 ? (await page.evaluate(() => window.__src)).join(" | ") : ""}`);
  check(page.errs.length === 0, `${label} ${scheme}: no page errors ${page.errs.join(" | ")}`);
  if (scheme === "light") {
    // full screen
    await page.click("[data-sk-full]"); await page.waitForTimeout(500);
    const box = await page.evaluate(() => { const r = document.querySelector(".sk-chart").getBoundingClientRect(); return [r.width, r.height, innerWidth, innerHeight]; });
    check(box[0] >= box[2] - 1 && box[1] >= box[3] - 1, `${label}: full screen fills the window ${box.join("x")}`);
    const cv = await page.evaluate(() => { const r = document.querySelector(".sk-cv").getBoundingClientRect(); return [r.width, r.height]; });
    check(cv[1] > 250, `${label}: full-screen chart is tall (${cv[1]}px)`);
    await page.screenshot({ path: path.join(outDir, `full-${label}-${scheme}.png`) });
    await page.keyboard.press("Escape"); await page.waitForTimeout(300);
    check(await page.evaluate(() => !document.querySelector(".sk-chart.is-full")), `${label}: Escape closes full screen`);
    // ranges: All shows back to listing
    await page.click('[data-sk-range="All"]'); await page.waitForTimeout(400);
    const rg = await page.evaluate(() => document.querySelector('[data-sk-range="All"]').getAttribute("aria-pressed"));
    check(rg === "true", `${label}: All is pressed`);
    await page.screenshot({ path: path.join(outDir, `stock-all-${label}-${scheme}.png`), clip: { x: 0, y: 0, width: viewport.width, height: Math.min(viewport.height, 900) } });
    // layers menu
    await page.click("[data-sk-layers]"); await page.click('[data-sk-layer="vol"]'); await page.waitForTimeout(200);
    check(await page.evaluate(() => JSON.parse(localStorage.getItem("sp-sk-layers")).vol === false), `${label}: Layers menu turns volume off and remembers it`);
    await page.click('[data-sk-layer="vol"]');
  }
  await ctx.close();
}
{ // never forecast, from search
  const ctx = await browser.newContext({ viewport: sizes[0][1], colorScheme: "light" }); await ctx.route(/^https?:\/\/(?!127\.0\.0\.1)/, r => r.abort());
  mode.stale = false; const page = await open(ctx, "#today", "FIXA"); await page.waitForSelector("#q");
  await page.fill("#q", "never"); await page.waitForSelector("#sr li[data-pick]"); await page.keyboard.press("Enter");
  await ready(page);
  check(await page.evaluate(() => document.querySelector(".sk h2")?.textContent.includes("Never Forecast")), "a stock never forecast opens from search with its chart");
  check(await page.evaluate(() => /No forecast yet/.test(document.querySelector("[data-sk-fc]").textContent)), "it says so plainly and offers Analyse");
  check(await page.evaluate(() => document.querySelectorAll(".sk-fact").length > 10 && !/…/.test(document.querySelector(".sk-facts").textContent)), "its facts are there");
  await page.screenshot({ path: path.join(outDir, "stock-nocall-1440-light.png"), fullPage: true });
  const before = reqLog.length;
  await page.click("[data-sk-analyse]"); await page.waitForTimeout(500);
  check(reqLog.slice(before).includes("POST /api/v2/jobs"), "Analyse sends a job");
  await ctx.close();
}
{ // list + pane
  const ctx = await browser.newContext({ viewport: sizes[0][1], colorScheme: "light" }); await ctx.route(/^https?:\/\/(?!127\.0\.0\.1)/, r => r.abort());
  mode.stale = false; const page = await open(ctx, "#watchlist", "FIXA"); await page.waitForSelector(".lp");
  const row = await page.$("[data-sel]"); if (row) { await row.click(); await page.waitForSelector("#lpp .sk-cv canvas", { timeout: 8000 }); await page.waitForTimeout(500); await page.screenshot({ path: path.join(outDir, "pane-1440-light.png") }); check(true, "the same screen opens in the pane beside a list"); }
  else check(false, "list row found");
  await ctx.close();
}
{ // zoom and pan with the wheel, and the readout under the cursor
  const ctx = await browser.newContext({ viewport: sizes[0][1], colorScheme: "light" }); await ctx.route(/^https?:\/\/(?!127\.0\.0\.1)/, r => r.abort());
  const page = await open(ctx, "#stock", "FIXA"); await ready(page);
  const box = await (await page.$(".sk-cv")).boundingBox();
  await page.mouse.move(box.x + 300, box.y + 120); await page.waitForTimeout(200);
  const r1 = await page.evaluate(() => document.querySelector("[data-sk-readout]").textContent);
  check(/Open .*Close .*Volume/.test(r1), "values under the cursor: " + r1.slice(0, 80));
  await page.mouse.move(box.x + box.width - 60, box.y + 120); await page.waitForTimeout(200);
  const r2 = await page.evaluate(() => document.querySelector("[data-sk-readout]").textContent);
  check(/Forecast: Likely/.test(r2), "values under the cursor in the forecast zone: " + r2.slice(0, 90));
  await page.click('[data-sk-zoom="in"]'); await page.waitForTimeout(200);
  check(await page.evaluate(() => !document.querySelector('[data-sk-range][aria-pressed="true"]')), "zoom in clears the range highlight");
  await page.click("[data-sk-reset]"); await page.waitForTimeout(200);
  check(await page.evaluate(() => document.querySelector('[data-sk-range="1Y"]').getAttribute("aria-pressed") === "true"), "Reset goes back to 1Y");
  mode.stale = true; await page.reload(); await ready(page);
  check(await page.evaluate(() => !!document.querySelector(".sk-ood .chip.amber") && !!document.querySelector("[data-sk-update]")), "out-of-date shows the amber chip and Update");
  await page.click(".sk-ood [data-sk-update]"); await page.waitForTimeout(4500);
  check(await page.evaluate(() => !document.querySelector(".sk-ood")), "after the job the forecast is fresh and the chip is gone");
  await ctx.close();
}
await browser.close(); server.close();
if (fails.length) { console.error(fails.length + " check(s) failed"); process.exit(1); }
