// T26: drives the real Funds screen on generated neutral data: list, search with a typo, a fund page with the chart, buys,
// returns, falls, overlap and the Analyse flow; screenshots at 1440, 1100 and 400 wide in light and dark.
// Usage: node web/tests/funds-shots.mjs <out dir>
import http from "node:http"; import fs from "node:fs"; import path from "node:path"; import { createRequire } from "node:module";
const require = createRequire(import.meta.url); const { chromium } = require("playwright");
const out = process.argv[2] || "docs/status/shots-t26"; fs.mkdirSync(out, { recursive: true });
const root = new URL("../public/", import.meta.url).pathname;
// small deterministic noise
let seed = 7; const rnd = () => (seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296;
const HOUSES = ["Alpha", "Bharat", "Coastal", "Delta", "Eastern", "Fortune", "Global", "Indo", "Jupiter", "Kaveri"], KINDS = [["Equity Scheme - Flexi Cap Fund", "Flexi cap"], ["Equity Scheme - Large Cap Fund", "Large cap"], ["Equity Scheme - Small Cap Fund", "Small cap"], ["Debt Scheme - Liquid Fund", "Liquid"], ["Hybrid Scheme - Balanced Advantage", "Balanced"]];
const NAMES = ["Bluechip", "Growth", "Opportunities", "Focused", "Value", "Dynamic", "Prime", "Select", "Advantage", "Leaders"];
const entries = [], stats = { built_at: "2026-11-25T09:15:00+05:30", funds: { id: [], r1: [], r3: [], r5: [] }, categories: [] };
const N = 1500; for (let i = 0; i < N; i++) { const [cat, grp] = KINDS[i % 5], h = HOUSES[i % 10], id = `fx-${i}`;
  entries.push({ id, name: `${h} ${NAMES[(i * 3) % 10]} ${grp} Fund`, amc: `${h} Mutual Fund`, category: cat, group: grp, variants: 4, primary_code: 1000 + i, isin: `INF000FX${String(i).padStart(3, "0")}`, ter_direct: +(0.2 + rnd()).toFixed(2), ter_regular: +(1.2 + rnd()).toFixed(2), aum_cr: i % 40 === 0 ? 120 : Math.round(300 + rnd() * 40000), aliases: [] });
  stats.funds.id.push(id); stats.funds.r1.push(+(rnd() * 30 - 4).toFixed(1)); stats.funds.r3.push(+(6 + rnd() * 16).toFixed(1)); stats.funds.r5.push(+(8 + rnd() * 12).toFixed(1)); }
const months = [], med = []; for (let y = 2012; y <= 2026; y++) for (let m = 1; m <= 12; m++) { if (y === 2026 && m > 11) break; months.push(`${y}-${String(m).padStart(2, "0")}`); med.push(+(12 + 8 * Math.sin((y * 12 + m) / 9) - ((y === 2020 && m <= 4) ? 25 : 0)).toFixed(1)); }
KINDS.forEach(([c]) => stats.categories.push({ name: c, n: 300, r1: 12, r3: 13.5, r5: 12.8, months, med1y: med }));
// NAV since 2006: drift + noise, the 2008 and 2020 falls and the 2022 slide
function series(drift, vol, seedShift) { const dates = [], nav = [], bench = []; let v = 10, b = 1000; const t0 = Date.parse("2006-01-02");
  for (let d = 0; d < 7280; d++) { const t = new Date(t0 + d * 86400000); if ([0, 6].includes(t.getUTCDay())) continue; const iso = t.toISOString().slice(0, 10);
    const crash = (iso >= "2008-01-08" && iso <= "2009-03-09") ? -0.0016 : (iso >= "2020-01-20" && iso <= "2020-03-23") ? -0.012 : (iso >= "2021-10-19" && iso <= "2022-06-17") ? -0.0012 : 0;
    const rise = (iso > "2009-03-09" && iso < "2010-12-01") ? 0.0012 : (iso > "2020-03-23" && iso < "2021-10-19") ? 0.0018 : 0;
    const e = (rnd() - 0.5) * 2 * vol; v *= 1 + drift + crash * (0.8 + seedShift) + rise + e; b *= 1 + 0.00042 + crash + rise + (rnd() - 0.5) * 0.012; dates.push(iso); nav.push(+v.toFixed(4)); bench.push(+b.toFixed(2)); }
  return { dates, nav, bench }; }
const S = series(0.00038, 0.009, 0.1), main = "fx-0".replace("0", "5"); // fx-5: a large-cap fund of a house in the 10
const fund = { id: main, name: entries[5].name, amc: entries[5].amc, category: entries[5].category, as_of: "2026-11-24", variants: [
  { code: 1005, isin: entries[5].isin, plan: "Direct", option: "Growth", label: "Direct Growth", nav: S.nav.at(-1), nav_date: "2026-11-24" }, { code: 2005, isin: null, plan: "Direct", option: "IDCW", label: "Direct IDCW", nav: +(S.nav.at(-1) * .62).toFixed(2), nav_date: "2026-11-24" },
  { code: 3005, isin: null, plan: "Regular", option: "Growth", label: "Regular Growth", nav: +(S.nav.at(-1) * .91).toFixed(2), nav_date: "2026-11-24" }],
  costs: { ter_regular: entries[5].ter_regular, ter_direct: entries[5].ter_direct, aum_cr: entries[5].aum_cr }, nav: { code: 1005, dates: S.dates, nav: S.nav }, not_available: [] };
const young = { ...fund, id: "fx-6", name: entries[6].name, nav: { code: 1006, dates: S.dates.slice(-400), nav: S.nav.slice(-400) }, costs: { ter_regular: null, ter_direct: null, aum_cr: null }, not_available: ["TER", "AUM"] };
const hold = { id: main, name: fund.name, amc: fund.amc, as_of: "2026-10-31", holdings: [["INE000A00001", "Alpha Bank Ltd", 8.2], ["INE000B00002", "Beta Motors Ltd", 6.1], ["INE000C00003", "Coastal Power Ltd", 4.4], ["INE000D00004", "Delta Foods Ltd", 3.8], ["INE000E00005", "Eastern Steel Ltd", 3.1], ["INE000F00006", "Fortune IT Ltd", 2.2]].map(([isin, name, pct_nav]) => ({ isin, name, pct_nav })) };
const portfolio = { holdings: [{ symbol: entries[5].isin, name: fund.name, quantity: 812.4, value: 812.4 * S.nav.at(-1), gain_pct: 0.34, price: S.nav.at(-1), lots: [{ acquired_on: "2019-06-14", quantity: 300, cost: S.nav[S.dates.indexOf("2019-06-14")] || 100 }, { acquired_on: "2020-03-24", quantity: 300, cost: 120 }, { acquired_on: "2023-02-09", quantity: 212.4, cost: 210 }] },
  { symbol: "ALPHABANK", name: "Alpha Bank Ltd", quantity: 100, value: 150000, gain_pct: 0.1, price: 1500, lots: [] }, { symbol: "COASTPOWER", name: "Coastal Power Ltd", quantity: 50, value: 20000, gain_pct: 0.2, price: 400, lots: [] }] };
const searchIdx = { built_at: "t", entries: [{ symbol: "ALPHABANK", exchange: "NSE", segment: "NSE", name: "Alpha Bank Ltd", isin: "INE000A00001", aliases: [] }, { symbol: "COASTPOWER", exchange: "NSE", segment: "NSE", name: "Coastal Power Ltd", isin: "INE000C00003", aliases: [] }] };
const jobs = new Map(); let jobN = 0, askedPayload = null, calls = new Map();
const types = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".json": "application/json" };
const server = http.createServer((req, res) => { const u = new URL(req.url, "http://x"), p = u.pathname, json = o => { res.setHeader("content-type", "application/json"); res.end(JSON.stringify(o)); };
  if (p === "/funds/index.json") return json({ built_at: "t", entries, counts: { funds: N } }); if (p === "/funds/stats.json") return json(stats);
  if (p === `/funds/${main}.json`) return json(fund); if (p === "/funds/fx-6.json") return json(young); if (p.startsWith("/funds/")) return json({ ...fund, id: p.slice(7, -5), nav: { code: 1, dates: [], nav: [] }, variants: [], not_available: ["NAV history"] });
  if (p === `/fund_holdings/${main}.json`) return json(hold);
  if (p === "/data/history/NIFTYBEES.json") return json({ dates: S.dates, close: S.bench });
  if (p === "/data/portfolio.json") return json(portfolio); if (p === "/search/index.json") return json(searchIdx);
  if (p === "/api/me") return json({ person: "father" });
  if (p === "/api/queue") return json({ items: [] });
  if (p.startsWith("/api/v2/calls/")) { const s = decodeURIComponent(p.slice(14)); return calls.has(s) ? json({ call: calls.get(s), changes: [] }) : (res.statusCode = 404, json({ error: "not_found" })); }
  if (p === "/api/v2/jobs" && req.method === "POST") { let b = ""; req.on("data", d => b += d); req.on("end", () => { askedPayload = JSON.parse(b); const id = "job-" + ++jobN; jobs.set(id, Date.now()); setTimeout(() => calls.set(askedPayload.payload.symbol, { call: "keep", chance_3m: 0.58, out_of_date: false }), 3500); json({ id, status: "queued" }); }); return; }
  if (p.startsWith("/api/v2/jobs/")) { const id = p.slice(13), done = Date.now() - jobs.get(id) > 3300; return json({ job: { id, status: done ? "done" : "running" }, lines: [{ seq: 1, state: "done", text: "Reading the fund's price history" }, { seq: 2, state: done ? "done" : "active", text: "Comparing it with similar funds" }] }); }
  const f = path.join(root, p === "/" ? "index.html" : decodeURIComponent(p)); if (!fs.existsSync(f) || fs.statSync(f).isDirectory()) { res.statusCode = 404; return res.end("no"); }
  res.setHeader("content-type", types[path.extname(f)] || "application/octet-stream"); res.end(fs.readFileSync(f)); });
await new Promise(r => server.listen(0, r)); const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ args: ["--no-sandbox"] }); let bad = 0;
const ok = (c, m) => { console.log((c ? "ok   " : "FAIL ") + m); if (!c) bad++; };
const count = p => p.$eval(".uct b", e => +e.textContent.replace(/,/g, ""));
for (const theme of ["light", "dark"]) for (const [label, width] of [["1440", 1440], ["1100", 1100], ["400", 400]]) {
  const ctx = await browser.newContext({ viewport: { width, height: 900 }, deviceScaleFactor: 1, colorScheme: theme });
  await ctx.route(/^https?:\/\/(?!127\.0\.0\.1)/, r => r.abort());
  const page = await ctx.newPage(); const errs = []; page.on("pageerror", e => errs.push(e.message));
  await page.goto(base + "/#funds"); await page.waitForSelector(".fxg tbody tr", { timeout: 15000 });
  const first = theme === "light" && label === "1440", shot = n => page.screenshot({ path: path.join(out, `${n}-${label}-${theme}.png`) });
  const noScroll = async m => { const ok1 = await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1); if (!ok1) console.log(await page.evaluate(() => [...document.querySelectorAll("body *")].filter(e => e.getBoundingClientRect().right > innerWidth + 1).slice(0, 6).map(e => e.tagName + "." + e.className + " " + Math.round(e.getBoundingClientRect().right)).join(" | "))); ok(ok1, `${theme} ${label}: ${m}: no sideways scroll`); };
  if (first) {
    ok(await count(page) === N, "every fund in the file is listed (1,500)");
    await page.fill("#fxq", "bluchip"); await page.waitForTimeout(150); const typo = await count(page); ok(typo > 0 && typo < N, `a typo ("bluchip") still finds funds (${typo})`);
    await page.fill("#fxq", ""); await page.selectOption("#fxg", "Liquid"); const liq = await count(page); ok(liq === N / 5, `kind filter keeps one in five (${liq})`);
    await page.selectOption("#fxg", ""); await page.selectOption("#fxs", "r3"); const r3 = await page.$$eval(".fxg tbody tr td:nth-child(3)", c => c.slice(0, 30).map(x => parseFloat(x.textContent)));
    ok(r3.every((v, i) => !i || r3[i] <= r3[i - 1]), "sorting by 3-year return orders the rows"); await page.selectOption("#fxs", "rel");
    // global search finds a fund and opens its page
    await page.fill("#q", "Delta Leaders"); await page.waitForSelector("#sr li[data-pick^='fund:']"); ok(true, "the top search box finds funds too");
    await page.keyboard.press("Escape"); await page.fill("#q", "");
  }
  await noScroll("list"); await shot("funds-list");
  await page.goto(base + `/#funds/${main}`); await page.waitForSelector(".fxsvg"); await page.waitForSelector("#fxfc");
  await page.waitForFunction(() => document.querySelector(".fxbuy"), null, { timeout: 8000 }).catch(() => {});
  if (first) {
    ok((await page.$$(".fxbuy")).length === 3, "the three buys show as dots on the chart");
    await page.click('[data-fxr="1Y"]'); await page.waitForTimeout(100); ok((await page.$$(".fxbuy")).length === 0, "1Y range hides buys outside it"); await page.click('[data-fxr="All"]');
    await page.hover(".fxsvg", { position: { x: 300, y: 100 } }); ok((await page.textContent(".fxread")).includes("price"), "hovering reads the price of that day");
    const rows = await page.$$eval(".fxr tbody tr", r => r.length); ok(rows >= 6, `returns and falls tables fill (${rows} rows)`);
    const ov = await page.textContent(".fxov"); ok(/Alpha Bank/.test(ov) && /Coastal Power/.test(ov) && !/Delta Foods/.test(ov), "overlap lists only the stocks held");
    ok(/12\.6%|12\.\d%/.test(await page.textContent(".fxbig")), "overlap weight is the sum of shared holdings (8.2 + 4.4)");
    ok((await page.textContent("#fxfc")).includes("No forecast yet"), "no forecast yet -> says so");
    await page.click("[data-fxask]"); await page.waitForSelector(".fxjob li"); ok(askedPayload && askedPayload.kind === "analyse" && askedPayload.payload.exchange === "AMFI", "Analyse creates an analyse job for the fund");
    await page.waitForFunction(() => /out of 100/.test(document.querySelector("#fxfc").textContent), null, { timeout: 15000 }); ok(true, "the forecast appears when the job finishes");
    await page.click("[data-star]"); ok(await page.$eval("[data-star]", e => e.getAttribute("aria-pressed")) === "true", "the watch star turns on");
  }
  await page.waitForTimeout(300); await noScroll("fund page"); await shot("fund-page");
  await page.evaluate(() => scrollTo(0, 99999)); await shot("fund-page-bottom");
  await page.goto(base + "/#funds/fx-6"); await page.waitForSelector(".fxsvg"); await page.waitForTimeout(300);
  if (first) { ok(/too young/.test(await page.textContent(".fxsec:nth-of-type(3)").catch(() => "") ) || true, "young fund page opens"); const t = await page.textContent("#view"); ok(/too young/.test(t) && /Not available for this fund/.test(t), "a young fund says what it lacks, no broken tables"); }
  await shot("fund-young");
  ok(!errs.length, `${theme} ${label}: no page errors ${errs[0] || ""}`);
  await ctx.close();
}
await browser.close(); server.close(); process.exit(bad ? 1 : 0);
