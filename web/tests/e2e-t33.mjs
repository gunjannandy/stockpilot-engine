// T33: click-every-button sweep. Serves web/public with the fixture site's data (tests/build_site_v10.py) and a tiny mock API,
// then on every screen clicks every button, link, filter, toggle and star, at 1440, 1100 and 400, light and dark, English and Bengali.
// Fails on: a page error, a console error, sideways scroll, "undefined"/"NaN"/"[object" in the text,
// a control that cannot be clicked, or a control that did nothing (no DOM, hash, class or toast change).
// Usage: node e2e-t33.mjs <site dir> [shots dir] [--quick]   (--quick: 1440 light English only)
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const args = process.argv.slice(2).filter(a => !a.startsWith("--"));
const quick = process.argv.includes("--quick");
const [dataDir, shotDir] = args;
if (!dataDir) { console.error("usage: node e2e-t33.mjs <site dir> [shots dir] [--quick]"); process.exit(2); }
const PUB = new URL("../public/", import.meta.url).pathname;
const types = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".json": "application/json" };
const ROUTES = (process.env.ROUTES || "today,calls,follow,watchlist,ideas,portfolio,funds,funds/F3,universe,market,record,settings,feedback,health").split(",");

// neutral synthetic public files the fixture site does not carry (funds, universe); ids are made up
const day = 86400000, mkNav = (n, start, rate) => { const dates = [], nav = []; for (let d = 0; d < n; d++) { dates.push(new Date(Date.parse("2021-01-01") + d * day).toISOString().slice(0, 10)); nav.push(+(start * Math.pow(1 + rate, d / 365) * (1 + 0.02 * Math.sin(d / 20))).toFixed(4)); } return { dates, nav }; };
const GROUPS = ["Large cap", "Flexi cap", "Index"], AMCS = ["Alpha Mutual Fund", "Beta Mutual Fund", "Gamma Mutual Fund"];
const FUNDS = Array.from({ length: 60 }, (_, i) => ({ id: "F" + i, name: `Sample Fund ${i} Growth`, amc: AMCS[i % 3], group: GROUPS[i % 3], category: GROUPS[i % 3], isin: "INF00000" + String(i).padStart(4, "0"), variants: 2, ter_direct: 0.3 + (i % 10) / 10, ter_regular: 1.2, aum_cr: 400 + i * 700 }));
const fundFile = id => { const e = FUNDS.find(x => x.id === id); if (!e) return null; const nav = mkNav(4300, 20, 0.12); return { id, name: e.name, amc: e.amc, category: e.category, variants: [{ code: "1", plan: "Direct", option: "Growth", label: "Direct Growth", nav: nav.nav.at(-1), nav_date: nav.dates.at(-1), ter: e.ter_direct }, { code: "2", plan: "Regular", option: "Growth", label: "Regular Growth", nav: nav.nav.at(-1) * 0.9, nav_date: nav.dates.at(-1), ter: 1.2 }], nav: { code: "1", ...nav }, not_available: [] }; };
const fundStats = { funds: { id: FUNDS.map(f => f.id), r1: FUNDS.map((_, i) => (i % 7) - 2), r3: FUNDS.map((_, i) => 8 + (i % 9)), r5: FUNDS.map((_, i) => 9 + (i % 5)) }, categories: GROUPS.map(g => ({ name: g, r1: 5, r3: 11, r5: 12 })) };
const holdings = { holdings: [{ isin: "INE000A00001", name: "Alpha Ltd", pct_nav: 6.5 }, { isin: "INE000B00002", name: "Beta Ltd", pct_nav: 3 }] };
const uni = (() => { const n = 250, t = { built_at: "t", symbol: [], exchange: [], segment: [], name: [], sector: [], pe: [], growth: [], chance_6m: [], mcap_cr: [], last: [], day_change_pct: [] }; for (let i = 0; i < n; i++) { t.symbol.push("S" + i); t.exchange.push(i % 3 ? "NSE" : "BSE"); t.segment.push(i % 3 ? (i % 7 ? "NSE" : "NSE_SME") : "BSE"); t.name.push(`Stock ${i} Limited`); t.sector.push(i % 5 === 0 ? null : "Sector " + (i % 4)); t.pe.push(i % 6 === 0 ? null : 5 + (i % 50)); t.growth.push(i % 8 === 0 ? null : (i % 40) - 10); t.chance_6m.push(i % 4 === 0 ? null : 0.3 + (i % 50) / 100); t.mcap_cr.push(i % 9 === 0 ? null : 100 * (1 + (i % 400))); t.last.push(10 + i); t.day_change_pct.push(0); } return t; })();
const synth = p => { let m; if (p === "/funds/index.json") return { entries: FUNDS }; if (p === "/funds/stats.json") return fundStats; if ((m = /^\/funds\/(F\d+)\.json$/.exec(p))) return fundFile(m[1]); if (/^\/fund_holdings\//.test(p)) return holdings; if (p === "/screen/universe.json") return uni; return undefined; };
const posted = [];
const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://x"), json = b => { res.setHeader("content-type", "application/json"); res.end(JSON.stringify(b)); };
  if (url.pathname === "/api/me") return json({ person: "father" });
  if (url.pathname === "/api/queue" && req.method === "GET") return json({ items: [] });
  if (url.pathname === "/api/queue" && req.method === "POST") { let b = ""; req.on("data", d => b += d); return req.on("end", () => { posted.push(b); json({ id: "q" + posted.length }); }); }
  if (url.pathname.startsWith("/api/v2/changes")) return json({ person: "father", unseen_count: 0, items: [] });
  { const sy = synth(url.pathname); if (sy !== undefined) { if (sy === null) { res.statusCode = 404; return res.end("no"); } return json(sy); } }
  if (url.pathname.startsWith("/api/")) { res.statusCode = 404; return json({}); }
  let file = path.join(PUB, url.pathname === "/" ? "index.html" : decodeURIComponent(url.pathname));
  if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) file = path.join(dataDir, decodeURIComponent(url.pathname));
  if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.statusCode = 404; return res.end("no"); }
  res.setHeader("content-type", types[path.extname(file)] || "application/octet-stream"); res.end(fs.readFileSync(file));
});
await new Promise(r => server.listen(0, "127.0.0.1", r));
const base = `http://127.0.0.1:${server.address().port}`;
if (shotDir) fs.mkdirSync(shotDir, { recursive: true });
const sleep = ms => new Promise(r => setTimeout(r, ms));
const browser = await chromium.launch({ args: ["--no-sandbox"] });
const problems = new Set(), stats = { clicks: 0, pages: 0 };

const SEL = 'button, a[href], [data-go], [data-open], [data-tab], [data-mode], [data-src], [role=button], [role=tab], summary, input, select, [data-f], [data-star], [data-lang], [data-themeset]';
const SIGSRC = `(e) => { const t = (e.innerText || e.value || e.getAttribute("aria-label") || e.title || "").replace(/\\s+/g, " ").trim().slice(0, 40); return [e.tagName, e.id, e.className && String(e.className).slice(0, 40), t, ...[...e.attributes].filter(a => a.name.startsWith("data-") || a.name === "href" || a.name === "tabindex").map(a => a.name + "=" + a.value.slice(0, 40))].join("|"); }`;

async function sweep(width, theme, lang) {
  const tag = `${width}-${theme}-${lang}`;
  const ctx = await browser.newContext({ viewport: { width, height: width < 500 ? 860 : 900 }, colorScheme: theme, deviceScaleFactor: 1 });
  const setPrefs = `try { localStorage.setItem("sp-lang", ${JSON.stringify(JSON.stringify(lang))}); localStorage.setItem("sp-theme", ${JSON.stringify(JSON.stringify(theme))}); } catch {}`;
  await ctx.addInitScript(setPrefs);
  const page = await ctx.newPage();
  let where = "";
  const bad = m => problems.add(`${tag} ${where}: ${m}`);
  page.on("pageerror", e => bad("page error " + String(e).slice(0, 160)));
  page.on("console", m => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) bad("console error " + m.text().slice(0, 160)); });
  page.on("dialog", d => d.dismiss().catch(() => {}));
  page.on("popup", p => p.close().catch(() => {}));
  const open = async hash => { await page.goto(base + "/#" + hash); await page.reload(); await page.waitForSelector("h1", { timeout: 8000 }).catch(() => bad("no heading")); await sleep(350); };
  const health = async () => {
    const r = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth - innerWidth, t: document.body.innerText }));
    if (r.sw > 2) bad(`sideways scroll ${r.sw}px`);
    const m = /undefined|NaN|\[object/.exec(r.t); if (m) bad(`text shows "${m[0]}"`);
  };
  const find = sig => page.evaluateHandle(([s, src, selr]) => { const S = eval(src); return [...document.querySelectorAll(selr)].find(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && S(e) === s; }) || null; }, [sig, SIGSRC, SEL]);
  for (const route of ROUTES) {
    where = route;
    await open(route); stats.pages++; await health();
    if (shotDir && !quick) await page.screenshot({ path: path.join(shotDir, `${route}-${tag}.png`) });
    const sigs = await page.evaluate(([src, selr]) => { const S = eval(src); return [...document.querySelectorAll(selr)].filter(e => { const r = e.getBoundingClientRect(), cs = getComputedStyle(e); return r.width > 0 && r.height > 0 && cs.visibility !== "hidden" && !e.disabled; }).map(S); }, [SIGSRC, SEL]);
    const seen = new Set();
    for (const sig of sigs) {
      if (seen.has(sig)) continue; seen.add(sig);
      where = `${route} [${sig.slice(0, 90)}]`;
      if (/href=(https?:|\/kite\/)|type=file|tabindex=-1/.test(sig)) continue;   // external links and file pickers are not ours to test
      const el = (await find(sig)).asElement(); if (!el) continue;   // an earlier click changed the page; the control is gone
      const snap = () => page.evaluate(() => ({ h: location.hash, c: document.body.innerHTML.replace(/\s+/g, "").length + ":" + [...document.body.innerText].reduce((a, ch, i) => (a * 31 + ch.charCodeAt(0) * (i % 97 + 1)) | 0, 7), cls: document.documentElement.className + document.documentElement.dataset.theme + document.documentElement.lang, t: document.body.innerText.length, y: scrollY, toast: !!document.querySelector(".toast") }));
      const before = await snap();
      stats.clicks++;
      const opened = await el.evaluate(e => { const d = e.closest("details:not([open])"); if (!d || e.tagName === "SUMMARY") return false; d.querySelector("summary").click(); return true; });   // a folded section: a person opens it first
      if (opened) await sleep(250);
      let target = el;
      for (let attempt = 0; attempt < 2; attempt++) {
        try { await target.scrollIntoViewIfNeeded({ timeout: 1500 }); await target.click({ timeout: 2500 }); break; }
        catch (e) {
          const msg = String(e).split("\n").slice(0, 8).join(" ").slice(0, 400);
          if (attempt === 0) { await open(route); target = (await find(sig)).asElement(); if (target) continue; }   // an earlier click folded or covered it: try again on a fresh page
          bad("could not click: " + msg); await open(route); target = null; break;
        }
      }
      if (!target) continue;
      await sleep(250);
      if (/^INPUT\|/.test(sig) && !/type=(checkbox|radio)/.test(sig)) { await page.keyboard.type("re", { delay: 20 }).catch(() => {}); await sleep(250); await page.keyboard.press("Escape"); }
      const sheetOpened = !!(await page.$("#scrim"));
      if (sheetOpened) { await page.mouse.click(width / 2, 40).catch(() => {}); await sleep(250); if (await page.$("#scrim")) { await page.keyboard.press("Escape"); await sleep(200); } if (await page.$("#scrim")) { bad("sheet does not close from its backdrop or Escape"); await open(route); continue; } }
      await health();
      const after = await snap();
      const changed = after.h !== before.h || after.c !== before.c || after.cls !== before.cls || after.t !== before.t || Math.abs(after.y - before.y) > 4 || after.toast || sheetOpened;
      const sameRoute = /^A\|.*href=#/.test(sig) && sig.endsWith("href=#" + route.split("/")[0])
      if (!changed && !sameRoute && !/^INPUT\||^SUMMARY\|/.test(sig) && !(/data-themeset=|data-lang=/.test(sig))) problems.add(`${tag} INERT ${where}`);
      const cur = await page.evaluate(() => location.hash.slice(1).split("/")[0]);
      if (after.h !== before.h || /data-lang|data-themeset|id=lang|id=theme/.test(sig) || cur !== route.split("/")[0]) await open(route);
    }
  }
  await ctx.close();
}

const widths = process.env.WIDTHS ? process.env.WIDTHS.split(",").map(Number) : quick ? [1440] : [1440, 1100, 400], themes = quick ? ["light"] : ["light", "dark"], langs = quick ? ["en"] : ["en", "bn"];
for (const w of widths) for (const t of themes) for (const l of langs) { await sweep(w, t, l); console.log(`done ${w} ${t} ${l}: ${problems.size} problems so far`); }
await browser.close(); server.close();
console.log(`pages ${stats.pages}, clicks ${stats.clicks}`);
if (problems.size) { console.log([...problems].sort().join("\n")); console.log(`FAIL: ${problems.size} problems`); process.exit(1); }
console.log("PASS: every control clicked, zero failures");
