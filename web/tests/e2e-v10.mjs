// v10 UI checks. Usage: node e2e-v10.mjs <site dir | https://url> [shots dir]
// A directory is served locally with a mock queue API; a URL is checked read-only (no clicks that post).
// At 1440, 1100 and 400, light and dark: no page errors, no sideways scroll, layout shift at most 0.02 per page,
// one scroll area per page, a pane that never changes size, a verdict word on every row, a hover tip on every chart,
// Back to the same list and row, stars and filters that patch the DOM, folds that stay folded.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const [target, shotDir] = process.argv.slice(2);
if (!target) { console.error("usage: node e2e-v10.mjs <site dir | url> [shots dir]"); process.exit(2); }
const remote = /^https?:/.test(target);
const types = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".json": "application/json" };
const posted = []; let capAsk = false;
let base = target.replace(/\/$/, ""), server = null;
if (!remote) {
  server = http.createServer((req, res) => {
    const url = new URL(req.url, "http://x");
    if (url.pathname === "/api/me") return res.end(JSON.stringify({ person: "Father" }));
    // T29: portfolio, smallcase, record and own_record come from /api/v2/views/<name>; serve them from the site's data files
    if (url.pathname.startsWith("/api/v2/changes")) { res.setHeader("content-type", "application/json"); return res.end('{"person":"father","unseen_count":0,"items":[]}'); }
    const vm = /^\/api\/v2\/views\/(\w+)$/.exec(url.pathname);
    if (vm) { const f = path.join(target, "data", vm[1] + ".json"); res.setHeader("content-type", "application/json"); if (!fs.existsSync(f)) { res.statusCode = 404; return res.end("{}"); } return res.end(JSON.stringify({ name: vm[1], as_of: "2026-11-20", written_at: "2026-11-20T18:00:00+05:30", doc: JSON.parse(fs.readFileSync(f, "utf8")) })); }
    const ck = /^\/chart\/([^/]+)\.json$/.exec(url.pathname); if (ck) { ck[1] = decodeURIComponent(ck[1]); } if (ck) { // T22: the chart file (OHLC); the site's history file has closes only, so open, high and low are the close
      const f = path.join(target, "data", "history", ck[1] + ".json"); if (!fs.existsSync(f)) { res.statusCode = 404; return res.end("no"); }
      const h = JSON.parse(fs.readFileSync(f, "utf8")); res.setHeader("content-type", "application/json");
      return res.end(JSON.stringify({ symbol: ck[1], exchange: "NSE", listed_on: h.dates[0], as_of: h.as_of, adjusted: true, dates: h.dates, open: h.close, high: h.close, low: h.close, close: h.close, volume: h.volume, dma50: h.dma50, dma200: h.dma200 })); }
    const sk = /^\/stock\/([^/]+)\.json$/.exec(url.pathname); if (sk) url.pathname = "/data/stock/" + sk[1] + ".json";   // T22: the stock page reads /stock/<symbol>.json
    if (url.pathname === "/api/queue" && req.method === "GET") { res.setHeader("content-type", "application/json"); return res.end('{"items":[]}'); }
    if (url.pathname === "/api/queue" && req.method === "POST") { let b = ""; req.on("data", d => b += d); return req.on("end", () => { const j = JSON.parse(b); posted.push(j); res.setHeader("content-type", "application/json"); if (capAsk && j.kind === "ask_analyst") { res.statusCode = 429; return res.end('{"error":"cap"}'); } res.end('{"id":1}'); }); }
    if (url.pathname.startsWith("/api/queue/")) return res.end("{}");
    const file = path.join(target, url.pathname === "/" ? "index.html" : decodeURIComponent(url.pathname));
    if (!file.startsWith(path.resolve(target)) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.statusCode = 404; return res.end("no"); }
    res.setHeader("content-type", types[path.extname(file)] || "application/octet-stream"); res.end(fs.readFileSync(file));
  });
  await new Promise(r => server.listen(0, "127.0.0.1", r));
  base = `http://127.0.0.1:${server.address().port}`;
}
if (shotDir) fs.mkdirSync(shotDir, { recursive: true });

const problems = [], info = [];
// T22: the pane has no "open full page" link; a [data-open] link anywhere opens the page (search and the lists use them)
let openPaneStock;
// F2: banned words come from prompts/plain-words.md ("- word →" lines); a reason line may not use one
const JARGON = fs.readFileSync(new URL("../../prompts/plain-words.md", import.meta.url), "utf8").split("\n").map(l => /^- ([^→]+?) →/.exec(l)?.[1]).filter(Boolean).filter(x => !/^(support|resistance|multiple)$/.test(x));
const jargonIn = t => JARGON.filter(j => new RegExp(`(^|[^a-z])${j.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}([^a-z]|$)`, "i").test(t));
const PAGES = ["today", "holdings", "follow", "watchlist", "ideas", "market", "tax", "tradrec", "record", "settings", "feedback", "health"];
const SHELL = ["today", "holdings", "follow", "watchlist", "ideas"];
// symbol -> reasoning object, read from the built site's own JSON (real objects, no fixture sentences)
const RZ = new Map();
if (!remote) for (const f of ["today", "calls", "watchlist", "ideas"]) { try { (function walk(x) { if (Array.isArray(x)) x.forEach(walk); else if (x && typeof x === "object") { if (x.symbol && x.reasoning && !RZ.has(x.symbol)) RZ.set(x.symbol, x.reasoning); Object.values(x).forEach(walk); } })(JSON.parse(fs.readFileSync(path.join(target, "data", f + ".json"), "utf8"))); } catch {} }
const hasReasons = sym => { const r = RZ.get(sym); return !!((r?.for || []).length || (r?.against || []).length); };

// R-ui: the RSU pane and the ServiceNow page show every number in data/portfolio.json -> rsu, in the page's own formats
const F = { inr: v => v == null ? "–" : "₹" + Math.round(v).toLocaleString("en-IN"), n0: v => Number(v).toLocaleString("en-IN"), pct: (v, d = 0) => (v * 100).toFixed(d) + "%", spct: v => (v > 0 ? "+" : "") + (v * 100).toFixed(1) + "%" };
let RSU = null;
try { RSU = JSON.parse(remote ? await (await fetch(base + "/data/portfolio.json")).text() : fs.readFileSync(path.join(target, "data", "portfolio.json"), "utf8")).rsu; } catch {}
const flat = t => t.replace(/\u2212/g, "-").replace(/\s+/g, " ");
const missing = (text, want) => want.filter(x => x != null && !flat(text).includes(flat(String(x))));
const ORDER_WORDS = /place order|buy now|sell now|execute|confirm (the )?(sale|order)/i;
const browser = await chromium.launch();
const sleep = ms => new Promise(r => setTimeout(r, ms));

const RUNS = [1440, 1100, 400].flatMap(w => ["dark", "light"].map(t => [w, t, w < 500 ? 860 : 900])).concat([[1366, "light", 768]]);
for (const [width, theme, height] of RUNS) {
  const tag = `${width}-${theme}` + (height === 768 ? "-short" : "");
  if (process.env.ONLY && !process.env.ONLY.split(",").includes(tag)) continue;   // ONLY=1440-dark runs one combination
  const ctx = await browser.newContext({ viewport: { width, height }, colorScheme: theme, deviceScaleFactor: 1 });
  await ctx.addInitScript(() => {
    window.__cls = 0; window.__sh = [];
    new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput) { window.__cls += e.value; window.__sh.push(e.value.toFixed(4) + " " + (e.sources || []).map(s => s.node && (s.node.className || s.node.nodeName)).join(",")); } }).observe({ type: "layout-shift", buffered: true });
  });
  if (!remote) {
    // The page asks for its fonts with display=optional: a font that is late on the first paint is dropped for that visit, and a runner's
    // fallback font is wider, so the 1366x768 fit check flaked. Here the test waits for the real font (block) so every run measures it.
    await ctx.route(/fonts\.googleapis\.com\/css2/, async r => { const res = await r.fetch(); await r.fulfill({ response: res, body: (await res.text()).replace(/display:\s*optional/g, "display:block") }); });
  }
  const p = await ctx.newPage();
  openPaneStock = () => p.evaluate(() => { const sym = document.querySelector("#lpp")?.dataset.sym; document.body.insertAdjacentHTML("beforeend", `<a href="#stock" data-open="${sym}" id="__o">x</a>`); document.getElementById("__o").click(); document.getElementById("__o").remove(); });
  p.on("pageerror", e => problems.push(`${tag} pageerror ${e.message}`));
  p.on("console", m => { if (m.type() === "error" && !/404|Failed to load resource/.test(m.text())) problems.push(`${tag} console ${m.text()}`); });
  const bad = (m) => problems.push(`${tag} ${m}`);
  const shot = async n => { if (shotDir) await p.screenshot({ path: path.join(shotDir, `${tag}-${n}.png`) }); };
  const settle = async () => { await p.evaluate(() => document.fonts.ready); await sleep(700); };
  const resetCls = () => p.evaluate(() => { window.__cls = 0; window.__sh = []; });
  const cls = () => p.evaluate(() => [window.__cls, window.__sh.slice(0, 3).join(" | ")]);
  const go = async h => { await resetCls(); await p.evaluate(h => { location.hash = h; }, h); await settle(); };

  await p.goto(`${base}/#today`, { waitUntil: "networkidle" }); await settle();
  { const [c, w] = await cls(); info.push(`${tag} today load CLS ${c.toFixed(3)}`); if (c > 0.02) bad(`today load: layout shift ${c.toFixed(3)} ${w}`); }
  await p.evaluate(() => { try { localStorage.clear(); } catch {} });

  // every page: no sideways scroll, not empty, layout shift, scroll areas
  for (const pg of PAGES) {
    await go(pg); await p.evaluate(() => scrollTo(0, 0)); await sleep(150);
    const m = await p.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth, len: document.querySelector("#view").innerText.length }));
    if (m.sw > m.cw + 1) bad(`${pg}: sideways scroll ${m.sw}>${m.cw}`);
    if (m.len < 150) bad(`${pg}: nearly empty (${m.len})`);
    const [c, w] = await cls(); if (c > 0.02) bad(`${pg}: layout shift ${c.toFixed(3)} ${w}`);
    if (width > 900 && SHELL.includes(pg)) {
      const sc = await p.evaluate(() => {
        const doc = document.documentElement.scrollHeight > innerHeight + 1;
        const own = [...document.querySelectorAll("body *")].filter(e => { const s = getComputedStyle(e); return /(auto|scroll)/.test(s.overflowY) && e.scrollHeight > e.clientHeight + 1 && e.clientHeight > 0; }).map(e => e.id || e.className);
        return { doc, own };
      });
      if (sc.doc) bad(`${pg}: page scrolls inside the shell`);
      const extra = sc.own.filter(c => !/lp-list|lpp|^rail$/.test(c)); /* T22: the stock pane scrolls inside itself */ if (extra.length) bad(`${pg}: extra scroll areas ${extra.join(",")}`);
    }
    if (SHELL.includes(pg)) {
      // F2: every row has a reason line (the strongest for/against reason), no banned jargon; with the contract, a weight pill on it
      const rl = await p.evaluate(() => [...document.querySelectorAll(".lrow")].map(r => ({ id: r.dataset.sel, line: r.querySelector(".ls")?.textContent.trim() || "", rz: !!r.querySelector(".ls .wp"), held: /^hold:(INF|NOW)/.test(r.dataset.sel) })));
      const empty = rl.filter(r => r.line.length < 6); if (empty.length) bad(`${pg}: ${empty.length} rows without a reason line (${empty.slice(0, 3).map(r => r.id)})`);
      const jg = rl.flatMap(r => jargonIn(r.line).map(j => `${r.id}: ${j}`)); if (jg.length) bad(`${pg}: jargon in a reason line: ${jg.slice(0, 3).join(" | ")}`);
      if (!remote) { const no = rl.filter(r => !r.rz && !r.held && hasReasons(r.id.split(":")[1])); if (no.length) bad(`${pg}: ${no.length} rows with reasons have no weight pill on the reason line (${no.slice(0, 3).map(r => r.id)})`); }
    }
    if (width > 900 && SHELL.includes(pg)) {
      const rows = await p.evaluate(() => [...document.querySelectorAll(".lrow")].filter(r => !r.querySelector(".chip")).length);
      if (rows) bad(`${pg}: ${rows} rows without a verdict word`);
    }
    await shot(pg);
  }

  if (width > 900) {
    // pane never changes size on selection; rows have verdict words; chart hover tip
    await go("today");
    const size = () => p.evaluate(() => { const e = document.querySelector("#lpp"); const b = e?.getBoundingClientRect(); return b ? `${Math.round(b.width)}x${Math.round(b.height)}` : null; });
    const s0 = await size(); await resetCls();
    for (let i = 0; i < 3; i++) { await p.keyboard.press("j"); await sleep(400); }
    if (s0 !== await size()) bad(`pane size changed ${s0} -> ${await size()}`);
    { const [c, w] = await cls(); if (c > 0.02) bad(`selecting rows: layout shift ${c.toFixed(3)} ${w}`); }
    await sleep(300);
    // T22: the pane is the stock component; its chart is a lightweight-charts canvas (its own crosshair, no #tip)
    if (!await p.locator(".lp-pane .sk-chart canvas").count()) bad(`pane chart missing for ${await p.evaluate(() => { const e = document.querySelector("#lpp"); return e?.dataset.sym + ": " + (e?.querySelector(".sk-chart")?.innerText || "no .sk-chart").slice(0, 80); })}`);

    // Back returns to the same list and row
    const before = await p.evaluate(() => ({ sel: document.querySelector("[data-sel][aria-selected=true]")?.dataset.sel, top: document.querySelector(".lp-list")?.scrollTop }));
    // T22: the pane has no "open full page" link; a [data-open] link anywhere opens the page (search and the lists use them)
    await openPaneStock(); await settle();
    if (!await p.evaluate(() => location.hash.startsWith("#stock"))) bad("open full page did not reach a stock page");
    await shot("stock");
    await p.locator("[data-back]").first().click(); await settle();
    const after = await p.evaluate(() => ({ hash: location.hash, sel: document.querySelector("[data-sel][aria-selected=true]")?.dataset.sel, top: document.querySelector(".lp-list")?.scrollTop }));
    if (after.hash !== "#today") bad(`Back went to ${after.hash}`);
    if (after.sel !== before.sel) bad(`Back lost the selected row ${before.sel} -> ${after.sel}`);

    // stars patch the DOM, no re-render (they post to the queue, so not against production)
    if (!remote) {
    await p.evaluate(() => { window.__mark = document.querySelector("#view .lp"); });
    const star = p.locator(".lrow [data-star]").first();
    if (await star.count()) {
      const wasOn = await star.getAttribute("aria-pressed"); await star.click({ force: true }); await sleep(250);
      const same = await p.evaluate(() => window.__mark && window.__mark === document.querySelector("#view .lp") && document.contains(window.__mark));
      if (!same) bad("star toggle re-rendered the page");
      if (await star.getAttribute("aria-pressed") === wasOn) bad("star toggle did not change");
      await star.click({ force: true }); await sleep(150);
    } else bad("no star on list rows");
    }

    // folds stay folded through a filter change
    const fold = p.locator("[data-fold]").last();
    if (await fold.count()) {
      const key = await fold.getAttribute("data-fold"); const open0 = await fold.getAttribute("aria-expanded");
      await fold.click(); await sleep(150); const open1 = await p.locator(`[data-fold="${key}"]`).getAttribute("aria-expanded");
      if (open1 === open0) bad("fold did not toggle");
      const chip = p.locator(".tools [data-chip]").nth(1);
      if (await chip.count()) {
        await p.evaluate(() => { window.__fb = document.querySelector(".tools"); window.__lp = document.querySelector("#lpp"); });
        await chip.click(); await sleep(250);
        const kept = await p.evaluate(() => window.__fb === document.querySelector(".tools") && window.__lp === document.querySelector("#lpp") && document.contains(window.__fb));
        if (!kept) bad("filter change re-rendered more than the rows");
        await p.locator(".tools [data-chip]").first().click(); await sleep(250);
        if (await p.locator(`[data-fold="${key}"]`).first().getAttribute("aria-expanded") !== open1) bad("fold state lost after a filter change");
      } else bad("no filter chips on Today");
      await p.locator(`[data-fold="${key}"]`).first().click();
    }
  } else {
    await go("today");
    await p.locator(".lrow").first().click(); await settle(); await shot("stock");
    await p.locator("[data-back]").first().click(); await settle();
    const h = await p.evaluate(() => location.hash); if (h !== "#today") bad(`Back went to ${h}`);
  }


  // every chart on the tab pages shows a hover tip
  for (const pg of ["market", "tradrec", "record", "tax"]) {
    await go(pg); await p.evaluate(() => scrollTo(0, 0));
    const n = await p.locator("#view svg.pc, #view svg.sp").count();
    for (let i = 0; i < Math.min(n, 6); i++) {
      const el = p.locator("#view svg.pc, #view svg.sp").nth(i); await el.evaluate(e => e.scrollIntoView({ block: "center" })); const bb = await el.boundingBox(); if (!bb || bb.height < 8) continue;
      await p.mouse.move(bb.x + bb.width * .3, bb.y + bb.height * .5); await p.mouse.move(bb.x + bb.width * .6, bb.y + bb.height * .5, { steps: 5 }); await sleep(120);
      if (!await p.evaluate(() => document.getElementById("tip").classList.contains("on"))) bad(`${pg}: chart ${i + 1} has no hover tip`);
    }
    const barsN = await p.locator("#view svg.bc").count();
    for (let i = 0; i < Math.min(barsN, 4); i++) { const r = p.locator("#view svg.bc").nth(i).locator("[data-tip]").first(); if (!await r.count()) bad(`${pg}: bar chart ${i + 1} has no hover tips`); }
  }
  // the full stock page: chart range buttons and toggles patch the chart only; a hidden block leaves no empty card
  await go("today"); await p.evaluate(() => { const r = document.querySelector(".lrow"); r && r.click(); });
  await p.evaluate(() => { const a = document.querySelector("#lpp [data-open]") || document.querySelector("[data-open]"); a && a.click(); }); await settle();
  if (await p.evaluate(() => location.hash.startsWith("#stock"))) {
    await p.evaluate(() => { window.__pg = document.querySelector("#view").firstElementChild; });
    const r1 = p.locator("[data-crng='1Y']"); if (await r1.count()) { await r1.click(); await sleep(250); if (await r1.getAttribute("aria-pressed") !== "true") bad("range button did not select"); }
    const tg = p.locator("[data-ctog='vol']"); if (await tg.count()) { await tg.click(); await sleep(150); if (!await p.evaluate(() => document.querySelector(".chartbox").classList.contains("no-vol"))) bad("volume toggle did not hide volume"); await tg.click(); }
    if (!await p.evaluate(() => window.__pg === document.querySelector("#view").firstElementChild)) bad("chart controls re-rendered the page");
    const empties = await p.evaluate(() => [...document.querySelectorAll("#view .card.wk, #view .pane")].filter(c => c.innerText.replace(/\s+/g, "").length < 4).length);
    if (empties) bad(`${empties} empty cards on the stock page`);
  } else bad("could not reach a stock page for the chart controls");

  // F2/F1: the pane and the stock page render the real `reasoning` objects the exporter wrote. Expectations are read from the site's own JSON, never from fixed sentences.
  if (!remote) {
    const J = f => { try { return JSON.parse(fs.readFileSync(path.join(target, "data", f), "utf8")); } catch { return null; } };
    const rzOf = r => [...(r?.for || []), ...(r?.against || [])].filter(x => x.text).sort((a, b) => Math.abs(b.weight || 0) - Math.abs(a.weight || 0));
    const topText = r => rzOf(r)[0]?.text || (r?.facts || []).find(f => f.text)?.text;
    const today = J("today.json") || {}, wlj = J("watchlist.json") || {}, idj = J("ideas.json") || {};
    const firstWith = (rows, pred) => (rows || []).find(r => r.symbol && r.reasoning && pred(r.reasoning));
    const hasPair = r => rzOf(r).length > 0 && r.chance?.explain;
    const targets = [
      ["today", "today", firstWith(["buy", "sell", "keep", "watch_triggers"].flatMap(g => today[g] || []), hasPair)],
      ["watchlist", "wl", firstWith(wlj.rows, hasPair) || firstWith(wlj.rows, r => rzOf(r).length)],
      ["ideas", "ideas", firstWith([...(idj.ranking || []), ...(idj.near_misses || [])], r => rzOf(r).length)],
    ];
    const openSym = async sym => { await p.evaluate(s => { document.body.insertAdjacentHTML("beforeend", `<a href="#stock" data-open="${s}" id="__o">x</a>`); document.getElementById("__o").click(); document.getElementById("__o").remove(); }, sym); await settle(); };
    if (width > 900) {
      for (const [pg, key, rowData] of targets) {
        if (!rowData) { bad(`${pg}: no row with a reasoning object in the built site`); continue; }
        const sym = rowData.symbol, top = topText(rowData.reasoning);
        await go(pg); await p.evaluate(() => { document.querySelectorAll("[data-fold]").forEach(f => f.getAttribute("aria-expanded") === "false" && f.click()); }); await sleep(100);
        const row = p.locator(`[data-sel="${key}:${sym}"]`); if (!await row.count()) { bad(`${pg}: no row ${sym}`); continue; }
        await row.first().evaluate(e => e.scrollIntoView({ block: "center" })); await row.first().click(); await sleep(700);
        const line = await row.first().locator(".ls").innerText(); if (!line.includes(top.slice(0, 24))) bad(`${pg} ${sym}: the reason line is not the strongest reason (${line} vs ${top})`);
        // T22/v2: the stock pane is the stock component. Its essentials: the price, the verdict chip, the chart area, no page error (checked for the whole run)
        const pn = await p.evaluate(() => { const e = document.querySelector("#lpp"); return { sym: e?.dataset.sym, root: e?.querySelector("[data-sk-root]")?.dataset.skRoot, px: (e?.querySelector("[data-sk-px]")?.textContent || "").trim(), chip: !!e?.querySelector(".sk-chips .chip, .sk-chips .tag"), chart: !!e?.querySelector(".sk-chart") }; });
        if (pn.root !== sym) bad(`${pg} ${sym}: the pane shows ${pn.root || "nothing"}`);
        if (!/₹\s?[\d,]+/.test(pn.px)) bad(`${pg} ${sym}: the pane shows no price (${pn.px})`);
        if (!pn.chip) bad(`${pg} ${sym}: the pane shows no verdict chip`);
        if (!pn.chart) bad(`${pg} ${sym}: the pane has no chart area`);
      }
    }
    // the full stock page (v2): header with price, chart area, facts area; the old Why/For-Against section was replaced by the forecast block fed by /api/v2/calls
    for (const sym of [...new Set([targets[0][2]?.symbol, targets[1][2]?.symbol].filter(Boolean))]) {
      await go("today"); await openSym(sym);
      const pg = await p.evaluate(() => ({ root: document.querySelector("[data-sk-root]")?.dataset.skRoot, px: (document.querySelector("[data-sk-px]")?.textContent || "").trim(), chart: !!document.querySelector(".sk-chart"), facts: !!document.querySelector("[data-sk-facts]"), fc: !!document.querySelector("[data-sk-fc]"), sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
      if (pg.root !== sym) bad(`stock ${sym}: the page shows ${pg.root || "nothing"}`);
      if (!/₹\s?[\d,]+/.test(pg.px)) bad(`stock ${sym}: no price on the page (${pg.px})`);
      if (!pg.chart || !pg.facts || !pg.fc) bad(`stock ${sym}: page lacks its ${[!pg.chart && "chart", !pg.facts && "facts", !pg.fc && "forecast"].filter(Boolean).join(", ")} block`);
      if (pg.sw > pg.cw + 1) bad(`stock ${sym}: sideways scroll`);
    }
  }

  // Bengali: one language per screen; an untranslated sentence carries the EN tag
  const miss = await p.evaluate(() => Object.keys(window.SP_WORDS.en).filter(k => !(k in window.SP_WORDS.bn)));
  if (miss.length) bad(`${miss.length} words without Bengali: ${miss.slice(0, 8).join(", ")}`);
  await p.evaluate(() => localStorage.setItem("sp-lang", '"bn"')); await p.reload({ waitUntil: "networkidle" }); await settle();
  for (const pg of ["today", "holdings", "market", "tax", "tradrec", "record", "health", "settings"]) {
    await go(pg); await p.evaluate(() => scrollTo(0, 0));
    const m = await p.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
    if (m.sw > m.cw + 1) bad(`bn ${pg}: sideways scroll`);
    const latin = await p.evaluate(() => [...document.querySelectorAll("#view h1,#view h2,#view h3,.card.wk .wk-p")].filter(e => !e.closest(".lp-pane")).filter(e => !/[\u0980-\u09FF]/.test(e.textContent) && !e.querySelector(".entag") && /[A-Za-z]{4,}/.test(e.textContent.replace(/Holdings|Nifty|Sell|Buy|Hold|Portfolio|Watchlist|Tax|Health|Settings|Trade|Market|Feedback|Stock|Data/g, ""))).map(e => e.textContent.trim().slice(0, 40)));
    if (latin.length) bad(`bn ${pg}: English without an EN tag: ${latin.slice(0, 3).join(" | ")}`);
  }
  await p.evaluate(() => localStorage.removeItem("sp-lang"));

  // lane work wired to the real contract: verdict words, words link, gaps, RSUs, ownership, ask and long-term buttons, stock load states, feedback prompt
  if (!remote) {
    await p.reload({ waitUntil: "networkidle" }); await settle();    // back to English
    const open = async sym => { await p.evaluate(s => { document.body.insertAdjacentHTML("beforeend", `<a href="#stock" data-open="${s}" id="__o">x</a>`); document.getElementById("__o").click(); document.getElementById("__o").remove(); }, sym); await settle(); };
    await go("today");
    const chips = await p.evaluate(() => [...document.querySelectorAll(".lrow .chip")].map(c => c.textContent.trim()));
    for (const word of ["Weak", "Review", "Buy"]) if (!chips.includes(word)) bad(`today: no row reads ${word} (${[...new Set(chips)].join(",")})`);
    const sellRow = await p.evaluate(() => [...document.querySelectorAll(".lrow")].filter(r => /^Review$/.test(r.querySelector(".chip")?.textContent.trim())).length);
    if (!sellRow) bad("today: no Review row");
    // U3: a Today row reads in two seconds: a labelled chance and a labelled money figure, no sparkline; the headline leads with one action
    const rowInfo = await p.evaluate(() => [...document.querySelectorAll(".lrow")].map(r => ({ txt: r.querySelector(".lr").innerText, spark: !!r.querySelector(".lsp,svg.sp") })));
    if (!rowInfo.length || rowInfo.some(r => !/\d+%\s*chance/.test(r.txt))) bad(`today: a row does not label its chance (${rowInfo.map(r => JSON.stringify(r.txt)).join(" ")})`);
    if (rowInfo.some(r => r.spark)) bad("today: a row still carries a sparkline");
    if (!rowInfo.some(r => /(worth|aim) ₹/.test(r.txt))) bad("today: no row labels its money (worth or aim)");
    const hd = await p.evaluate(() => { const h = document.querySelector(".lead h1"), g = document.querySelector(".lead .glance"); return { h1: h.innerText, then: document.querySelector(".lead .then")?.innerText || "", hb: h.getBoundingClientRect().bottom, gt: g.getBoundingClientRect().top, gfs: parseFloat(getComputedStyle(g.querySelector(".k")).fontSize), hfs: parseFloat(getComputedStyle(h).fontSize), h1lines: Math.round(h.getBoundingClientRect().height / parseFloat(getComputedStyle(h).lineHeight)) }; });
    if (!/^(Sell|Look at|Review|Consider buying) .+ first\.$/.test(hd.h1)) bad(`today: the headline does not lead with one action: ${hd.h1}`);
    if (!/^After that: /.test(hd.then)) bad("today: no 'After that' line under the headline");
    if (hd.gt < hd.hb - 1) bad("today: the stat strip sits beside or above the headline"); if (hd.gfs > 13.5 || hd.gfs >= hd.hfs / 1.5) bad(`today: the stat strip is too loud (${hd.gfs}px)`);
    // U3: Review and Watch chips and stripes are not the selected-row blue
    const blues = await p.evaluate(() => { const probe = document.createElement("i"); probe.style.color = "var(--pri)"; document.body.append(probe); const pri = getComputedStyle(probe).color; probe.remove();
      const chipFor = w => [...document.querySelectorAll(".lrow .chip, .lg .chip")].find(c => c.textContent.trim() === w);
      const out = {}; for (const word of ["Review", "Watch"]) { const c = chipFor(word); if (c) { const cs = getComputedStyle(c); out[word] = [cs.backgroundColor, cs.color, cs.boxShadow].some(v => v.includes(pri)); } } return out; });
    if (blues.Review !== false) bad("today: the Review chip shares the selected-row blue (or is missing)");
    await p.evaluate(() => document.querySelector('[data-fold^="todaywatch"]')?.click()); await sleep(100);
    if ((await p.evaluate(() => [...document.querySelectorAll(".lrow .chip")].some(c => c.textContent.trim() === "Watch"))) && blues.Watch !== false) bad("today: the Watch chip shares the selected-row blue");
    await p.locator("[data-words]").first().click(); await sleep(150);
    if (!await p.evaluate(() => /Review:/.test(document.querySelector("#wdlg")?.innerText || "") && /Sell:/.test(document.querySelector("#wdlg")?.innerText || ""))) bad("words link did not open the words dialog");
    await p.keyboard.press("Escape"); await sleep(100); if (await p.locator("#wdlg").count()) bad("Escape did not close the words dialog");
    await go("holdings"); if (!await p.evaluate(() => [...document.querySelectorAll("#view .chip")].some(c => c.textContent.trim() === "RSU"))) bad("holdings: no RSU row for the group RSUs");
    await go("health"); if (!await p.evaluate(() => /Nippon India Gold/.test(document.querySelector("#view").innerText))) bad("health: the gaps card does not list the gap");
    if (!await p.evaluate(() => [...document.querySelectorAll("#view .next")].some(n => /^Next step:/.test(n.textContent)))) bad("health: a warning has no one-line next step");
    // U3: the long-term mark comes from the site file and survives a reload with no local state; the stock pane shows the analyst's note
    await go("holdings"); await p.locator('[data-sel="hold:HDFCBANK"]').click(); await sleep(500);
    await p.evaluate(() => localStorage.removeItem("sp-ltm")); await p.reload({ waitUntil: "networkidle" }); await settle(); await go("today"); await open("ITC");
    if (!await p.evaluate(() => document.querySelector("[data-ltm]")?.getAttribute("aria-pressed") === "true")) bad("stock: a holding marked held-for-years in the site file does not show the mark after a reload");
    await go("feedback"); if (!await p.evaluate(() => /What should we change/.test(document.querySelector("#view").innerText))) bad("feedback: no short prompt");
    // T22: a stock file that fails to load shows a plain message and a retry; a good one shows who owns the company
    await p.route("**/stock/TCS.json", r => r.fulfill({ status: 500, body: "x" }));
    await go("today"); await open("TCS");
    if (!await p.evaluate(() => /did not load/.test(document.querySelector("[data-sk-facts]")?.innerText || ""))) bad("stock: no failure message when the stock file fails");
    await p.unroute("**/stock/TCS.json"); await p.locator("[data-sk-retry]").first().click(); await sleep(600);
    if (!await p.evaluate(() => /pledged/i.test(document.querySelector("[data-sk-facts]")?.innerText || ""))) bad("stock: retry did not show the ownership numbers");
    await go("today"); await open("INFY");
    posted.length = 0;
    await p.locator("[data-ltm]").click(); await sleep(250);
    if (!posted.some(q => q.kind === "long_term_mark" && q.payload.symbol === "INFY" && q.payload.on === true)) bad("I hold this for years did not post long_term_mark on");
    // T22 removed the "Ask the analyst" box (the stock page now has Analyse, a job on /api/v2/jobs); its 429 sentence is covered by the jobs tests
    await p.evaluate(() => localStorage.removeItem("sp-ltm"));
  }

  // search opens a stock from anywhere
  await go("today"); await p.click("#q"); await p.keyboard.type("tata", { delay: 20 }); await sleep(300); await p.keyboard.press("Enter"); await settle();
  if (!await p.evaluate(() => location.hash.startsWith("#stock"))) bad("search did not open a stock");
  await shot("search");

  // R-ui: RSU pane (desktop) and ServiceNow page (every width) against portfolio.rsu
  if (RSU) {
    const r = RSU, t = r.tax_if_sold?.all, num = [F.n0(r.shares), F.inr(r.cost_inr), F.inr(r.value_inr), F.inr(Math.abs(r.profit_inr)), F.spct(r.profit_pct).replace("-", "-"), F.pct(r.share_of_portfolio, 0), F.pct(r.limit, 0)];
    const callWant = r.call ? [F.n0(r.call.shares), r.call.why, r.call.tax_line] : [];
    await go("holdings"); await resetCls();
    if (width > 900) {
      await p.locator('[data-sel="hold:NOW"]').click(); await sleep(600);
      const pane = await p.evaluate(() => document.querySelector("#lpp")?.innerText || "");
      const miss = missing(pane, [...num, ...callWant, r.statement.note, r.statement.real_shares + " confirmed", r.statement.estimated_shares + " estimated"]); if (miss.length) bad(`RSU pane misses ${miss.join(" | ")}`);
      if (ORDER_WORDS.test(pane)) bad("RSU pane has an order word"); if (await p.locator("#lpp .rsu-call button, #lpp .rsu-call [data-order]").count()) bad("RSU call card has a button");
      const [c, sh] = await cls(); if (c > 0.02) bad(`RSU pane: layout shift ${c.toFixed(3)} ${sh}`);
      await shot("rsu-pane");
      await openPaneStock(); await settle();
    } else { await p.locator('[data-sel="hold:NOW"]').click(); await settle(); }
    await resetCls(); await p.locator("#s-rsu").scrollIntoViewIfNeeded(); await sleep(300);
    const sec = await p.evaluate(() => document.querySelector("#s-rsu")?.innerText || "");
    if (!sec) bad("ServiceNow page has no RSU block");
    else {
      const rows = r.lots.flatMap(l => [F.n0(l.quantity), F.inr(l.cost_per_share_inr), F.inr(l.cost_inr), F.inr(l.value_inr), F.inr(Math.abs(l.gain_inr))]);
      const taxWant = t ? (t.net_gain_inr < 0 && !t.tax_inr ? [`No tax, a loss of ${F.inr(-t.net_gain_inr)}`, "set it against other gains"] : [F.inr(t.tax_inr)]) : [];
      const miss = missing(sec, [...num, ...rows, ...taxWant, ...callWant, r.statement.note, r.tax_if_sold?.note]); if (miss.length) bad(`RSU block misses ${miss.slice(0, 4).join(" | ")}`);
      const est = r.lots.filter(l => l.origin === "estimate").length, shown = await p.locator("#s-rsu .rsu-est").count();
      if (shown !== est) bad(`RSU block labels ${shown} lots estimated, data has ${est}`);
      if (await p.locator("#s-rsu tbody tr").count() !== r.lots.length) bad("RSU lots table row count differs from the data");
      for (const l of r.lots) if (l.term === "short" && !flat(sec).includes("Short-term until")) bad("RSU short-term lot not worded");
      for (const x of r.expected_vests || []) if (!sec.includes(F.n0(x.quantity)) || !/not confirmed/.test(sec)) bad("RSU expected vests not shown as unconfirmed");
      if (ORDER_WORDS.test(sec)) bad("RSU block has an order word"); if (await p.locator("#s-rsu button").count()) bad("RSU block has a button");
      const ovf = await p.evaluate(() => { const e = document.querySelector("#s-rsu"); return e.scrollWidth > e.clientWidth + 1 || document.documentElement.scrollWidth > document.documentElement.clientWidth + 1; }); if (ovf) bad("RSU block runs sideways");
    }
    const [c2, sh2] = await cls(); if (c2 > 0.02) bad(`RSU page: layout shift ${c2.toFixed(3)} ${sh2}`);
    await shot("rsu-stock");
  } else info.push(`${tag} no RSU in portfolio.json (RSU checks skipped)`);
  await ctx.close();
}
await browser.close(); server?.close();
console.log(info.join("\n")); console.log(problems.length ? "PROBLEMS\n" + problems.join("\n") : "all checks pass");
process.exit(problems.length ? 1 : 0);
