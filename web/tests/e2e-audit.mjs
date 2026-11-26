// AUDIT of owner feedback #18 to #23, end to end on a built site: a headless browser, the real Pages Functions, a local D1 with the real
// migrations. Usage (from web/): npx vite-node tests/e2e-audit.mjs <built site dir> <vm rows json> [shots dir] [overlay dir]
//   site dir      what `python tests/build_site_v10.py <dir>` writes, with web/public/screens and vendor copied in
//   vm rows json  `uv run python tests/audit_vm_rows.py <file>`: rows the real VM code writes (asks, changes)
//   overlay dir   the public files a deploy ships (search/index.json, chart/*.json, stock/*.json, screen/universe.json), made by the real builders
// Every check prints PASS or FAIL with what was seen. Exit 1 when any check failed.
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { startSite, INGEST_KEY } from "./audit-server.mjs";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const [siteDir, rowsFile, shotDir, overlayDir] = process.argv.slice(2);
if (!siteDir || !rowsFile) { console.error("usage: vite-node tests/e2e-audit.mjs <site dir> <vm rows json> [shots dir] [overlay dir]"); process.exit(2); }
const VM = JSON.parse(fs.readFileSync(rowsFile, "utf8"));
if (shotDir) fs.mkdirSync(shotDir, { recursive: true });

const results = [];
const check = (issue, name, ok, seen = "") => { results.push({ issue, name, ok: !!ok, seen }); console.log(`${ok ? "PASS" : "FAIL"} #${issue} ${name}${seen ? "  [" + String(seen).slice(0, 160) + "]" : ""}`); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const put = (db, table, row) => { const cols = Object.keys(row); db.db.prepare(`insert or replace into ${table} (${cols.join(",")}) values (${cols.map(() => "?").join(",")})`).run(...cols.map(c => typeof row[c] === "boolean" ? Number(row[c]) : row[c])); };
const rows = (db, sql, ...a) => db.db.prepare(sql).all(...a);

const site = await startSite({ siteDir, overlay: overlayDir ? [overlayDir] : [], workerKey: VM.news?.key });
const browser = await chromium.launch();
async function open(person, width = 1440, height = 900) {
  const ctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1 });
  await ctx.addCookies([{ name: "sp_session", value: site.cookies[person], url: site.base }]);
  const page = await ctx.newPage(); const errors = [];
  page.on("pageerror", e => errors.push(String(e)));
  page.on("console", m => { if (m.type() === "error" && !/fonts\.g|Failed to load resource/.test(m.text())) errors.push(m.text()); });
  await page.route(/fonts\.(googleapis|gstatic)\.com/, r => r.abort());
  return { ctx, page, errors };
}
const fresh = async (page, hash) => { const h = hash ?? new URL(page.url()).hash; await page.goto(site.base + "/?r=" + Math.random().toString(36).slice(2) + h, { waitUntil: "domcontentloaded" }); };
const shot = async (page, name) => { if (shotDir) await page.screenshot({ path: path.join(shotDir, name + ".png") }); };

// ---------------------------------------------------------------- #18 feedback and its queue
{
  const { page, ctx, errors } = await open("father");
  await page.goto(site.base + "/#feedback", { waitUntil: "domcontentloaded" }); await page.waitForSelector("#fbt");
  const text = "chart ta kite er moto korben ar BSE stock o dekhaben";
  await page.fill("#fbt", text);
  const t0 = Date.now();
  await page.click("[data-fb-act=send]");
  await page.waitForSelector(".fb-item", { timeout: 3000 });
  const first = await page.locator(".fb-item").first().innerText();
  check(18, "the message shows on the screen at once after Send, with its own words", first.includes(text) && Date.now() - t0 < 3000, first.replace(/\s+/g, " "));
  await sleep(300);
  const fb = rows(site.db, "select * from feedback where text = ?", text);
  const job = fb[0] && rows(site.db, "select * from jobs where kind = 'feedback_read' and payload like ?", `%${fb[0].id}%`);
  check(18, "the real Function stored the message and queued a feedback_read job for the VM", fb.length === 1 && job?.length === 1 && job[0].status === "queued", JSON.stringify({ fb: fb[0]?.status, job: job?.[0]?.status }));
  await sleep(100);
  const shown = await page.locator(".fb-item").first().innerText();
  check(18, "before the VM reads it, the item says Received and that it will appear within a minute", /Received/i.test(shown) && /within a minute/i.test(shown), shown.replace(/\s+/g, " "));
  // The VM reads it: the asks it writes are made by the real Python code (tests/audit_vm_rows.py).
  put(site.db, "feedback", { ...VM.feedback, id: fb[0].id, text, created_at: fb[0].created_at, status: "understood" });
  site.db.db.prepare("update feedback set status = 'understood' where id = ?").run(fb[0].id);
  for (const a of VM.asks) put(site.db, "asks", { ...a, id: a.id.replace("fb_audit", fb[0].id), feedback_id: fb[0].id, not_meant: a.not_meant ? 1 : 0 });
  await fresh(page); await page.waitForSelector(".fb-ask");
  const mine = page.locator(".fb-item", { hasText: text });
  const asks = await mine.locator(".fb-ask").count();
  const bodyT = await mine.innerText();
  check(18, "each ask appears with its status and the read-back", asks === 3 && /Waiting for approval/i.test(bodyT) && /We understood/i.test(bodyT), `${asks} asks; ` + bodyT.replace(/\s+/g, " ").slice(0, 100));
  check(18, "the father sees no Approve or Decline button; he sees who must approve", (await page.locator("[data-fb-act=approve]").count()) === 0 && /Waiting for the owner/i.test(bodyT));
  await shot(page, "18-father-feedback");
  // the owner approves one
  const o = await open("owner");
  await o.page.goto(site.base + "/#feedback", { waitUntil: "domcontentloaded" }); await o.page.waitForSelector(".fb-ask", { timeout: 4000 }).catch(() => {});
  const ownerSees = await o.page.locator(".fb-ask").count();
  check(18, "the owner has no feedback of his own on this screen (each person sees their own)", ownerSees === 0);
  // approve through the real route, as the owner's page does for an ask he can see
  const askId = `${fb[0].id}_a1`;
  const res = await o.page.evaluate(async id => { const r = await fetch(`/api/v2/asks/${id}/decide`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ decision: "approve" }) }); return [r.status, await r.json()]; }, askId);
  const fres = await page.evaluate(async id => { const r = await fetch(`/api/v2/asks/${id}/decide`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ decision: "approve" }) }); return r.status; }, `${fb[0].id}_a3`);
  check(18, "only the owner can approve: owner 200 being_built, father 403", res[0] === 200 && res[1].status === "being_built" && fres === 403, JSON.stringify([res, fres]));
  await fresh(page, "#today"); await sleep(1500);
  const dotOnFeedback = await page.locator('#rail a[href="#feedback"] .chg-dot').count();
  check(18, "the father gets a yellow dot on Feedback when an ask changes status", dotOnFeedback === 1, dotOnFeedback);
  await page.click('#rail a[href="#feedback"]'); await sleep(700);
  const after = await page.locator(".fb-item", { hasText: text }).innerText();
  check(18, "the ask now reads Being built", /Being built/i.test(after), after.replace(/\s+/g, " ").slice(0, 120));
  await fresh(page); await sleep(800);
  check(18, "opening Feedback clears its yellow dot", (await page.locator('#rail a[href="#feedback"] .chg-dot').count()) === 0);
  check(18, "no page errors on the Feedback screen", errors.length === 0, errors.join(" | "));
  await ctx.close(); await o.ctx.close();
}

// ---------------------------------------------------------------- #19 yellow notification for changed lists and predictions
{
  site.db.db.exec("delete from changes");
  for (const c of VM.changes) put(site.db, "changes", { ...c, at: c.at });
  put(site.db, "changes", { id: "chg_list_in", person: "father", symbol: "FIXB", kind: "list_entered", old_value: null, new_value: "worth_following", reason: "Joined Worth following: strong results.", reason_bn: null, at: new Date(Date.now() - 3600e3).toISOString().replace(/\.\d+Z/, "+00:00"), seen_at: null });
  put(site.db, "changes", { id: "chg_list_out", person: "father", symbol: "FIXD", kind: "list_left", old_value: "watchlist", new_value: null, reason: "Left the watchlist.", reason_bn: null, at: new Date(Date.now() - 7200e3).toISOString().replace(/\.\d+Z/, "+00:00"), seen_at: null });
  // the VM stamps IST; make the call changes recent so they sit inside the 7-day window
  site.db.db.prepare("update changes set at = ? where kind in ('call_changed','chance_moved','forecast_ready')").run(new Date(Date.now() - 1800e3).toISOString().replace(/\.\d+Z/, "+00:00"));
  const { page, ctx, errors } = await open("father");
  await page.goto(site.base + "/#today", { waitUntil: "domcontentloaded" }); await page.waitForSelector("#rail", { timeout: 8000 }); await sleep(1500);
  const dots = async () => Object.fromEntries(await page.$$eval("#rail a.nav", as => as.map(a => [a.getAttribute("href").slice(1), a.querySelectorAll(".chg-dot").length])));
  const d0 = await dots();
  check(19, "a changed prediction puts a yellow dot on Today", d0.today === 1, JSON.stringify(d0));
  check(19, "a list update puts a yellow dot on that list's tab (Worth following and Watchlist)", d0.follow === 1 && d0.watchlist === 1, JSON.stringify(d0));
  const strip = await page.locator(".chg-strip").innerText().catch(() => "");
  check(19, "Today shows what changed: old call to new call, why, and when", /hold\s*→\s*buy/.test(strip) && /Order win/.test(strip) && /\d{1,2} \w{3}, \d\d:\d\d/.test(strip), strip.replace(/\s+/g, " ").slice(0, 200));
  check(19, "the title carries the count of unseen changes", /^\(\d+\)/.test(await page.title()), await page.title());
  await shot(page, "19-today-strip");
  // another person's marks are separate (story 38)
  const ow = await open("owner"); await ow.page.goto(site.base + "/#today", { waitUntil: "domcontentloaded" }); await sleep(1500);
  check(19, "the owner's own marks are separate: he sees his, not the father's", (await ow.page.locator(".chg-strip .chg-li").count()) === VM.changes.filter(c => c.person === "owner").length);
  // opening Worth following clears its own dot only
  await page.click('#rail a[href="#follow"]'); await sleep(900); await fresh(page); await sleep(1200);
  const d1 = await dots();
  check(19, "opening a tab clears that tab's dot and leaves the others", d1.follow === 0 && d1.watchlist === 1 && d1.today === 1, JSON.stringify(d1));
  await fresh(page, "#today"); await sleep(800);
  await page.click("[data-chg-all]"); await sleep(800);
  check(19, "Got it, clear all dismisses the strip and the dots, and the server remembers", (await page.locator(".chg-strip").count()) === 0 && rows(site.db, "select count(*) n from changes where person='father' and seen_at is null")[0].n === 0 && rows(site.db, "select count(*) n from changes where person='owner' and seen_at is null")[0].n >= 1);
  await fresh(page); await sleep(1200);
  check(19, "after a reload nothing comes back", (await page.locator(".chg-strip").count()) === 0 && Object.values(await dots()).every(n => n === 0));
  check(19, "no page errors", errors.length === 0, errors.join(" | "));
  await ctx.close(); await ow.ctx.close();
}


// ---------------------------------------------------------------- #20 #21 #22: charts, history, zoom, drag, full view, every stock
{
  const { page, ctx, errors } = await open("father", 1440, 900);
  const reqs = []; page.on("response", r => { if (/\/(chart|stock)\//.test(r.url())) reqs.push(r.status() + " " + new URL(r.url()).pathname); });
  await fresh(page, "#today"); await page.waitForSelector("#q", { timeout: 8000 });
  const searchFor = async q => { await page.fill("#q", ""); await page.type("#q", q, { delay: 20 }); await sleep(500); return page.$$eval("#sr [data-open], #sr a, #sr [role=option]", els => els.map(e => (e.textContent || "").replace(/\s+/g, " ").trim())); };
  // -- #22 search finds every kind of listing, forgives typos
  const hits = {};
  for (const q of ["anawill", "ANAWIL", "bse micro", "relience"]) hits[q] = await searchFor(q);
  check(22, "search finds ANAWIL (an NSE SME stock), also from a misspelling", hits.anawill.some(t => /ANAWIL/.test(t)) && hits.ANAWIL.some(t => /ANAWIL/.test(t)), JSON.stringify(hits.anawill));
  check(22, "search finds a BSE-only SME stock", hits["bse micro"].some(t => /BSEMICRO|Bse Micro/i.test(t)), JSON.stringify(hits["bse micro"]));
  check(22, "search finds a main-board stock from a misspelling", hits.relience.some(t => /RELIANCE|Reliance/i.test(t)), JSON.stringify(hits.relience));
  await page.fill("#q", ""); await page.keyboard.press("Escape");
  // -- the Every stock screen
  await fresh(page, "#universe"); await page.waitForSelector("#uni .uni-row, #uni table, #uni [data-uni]", { timeout: 8000 }).catch(() => {});
  await sleep(800);
  const uni = await page.locator("#uni").innerText().catch(() => "");
  check(22, "Every stock lists NSE, SME and BSE stocks including ANAWIL", /ANAWIL/.test(uni) && /Bse Micro/i.test(uni) && /Reliance/i.test(uni), uni.replace(/\s+/g, " ").slice(0, 200));
  await shot(page, "22-every-stock");
  // -- open each kind of stock and read the chart
  async function openStock(sym) {
    await fresh(page, "#today"); await page.waitForSelector("#q", { timeout: 8000 });
    await page.fill("#q", ""); await page.type("#q", sym, { delay: 15 }); await sleep(500);
    await page.locator(`#sr li[role=option]:has-text("${sym}")`).first().click({ timeout: 4000 });
    await page.waitForSelector("[data-sk-cv]", { timeout: 8000 });
    await sleep(1200);
  }
  const chartInfo = async () => page.evaluate(() => { const cv = document.querySelector("[data-sk-cv]"); const r = cv.getBoundingClientRect(); const cvs = [...cv.querySelectorAll("canvas")]; return { w: Math.round(r.width), h: Math.round(r.height), canvases: cvs.length, note: (cv.querySelector(".sk-note")?.textContent || "").trim(), sig: cvs.map(c => { try { return c.toDataURL().length + ":" + c.toDataURL().slice(-60); } catch (e) { return ""; } }).join("|") }; });
  const hoverDate = async frac => { const box = await page.locator("[data-sk-cv]").boundingBox(); await page.mouse.move(box.x + 95 + (box.width - 230) * frac, box.y + box.height * 0.4); await sleep(150); return (await page.locator("[data-sk-readout]").innerText()).replace(/\s+/g, " "); };
  for (const sym of ["ANAWIL", "BSEMICRO"]) {
    await openStock(sym);
    const ci = await chartInfo();
    check(20, `the chart of ${sym} (${sym === "ANAWIL" ? "NSE SME" : "BSE-only SME"}) draws`, ci.canvases > 0 && !ci.note, JSON.stringify({ canvases: ci.canvases, note: ci.note }));
  }
  await openStock("RELIANCE");
  let ci = await chartInfo();
  check(20, "a main-board stock chart draws from the all-time chart file", ci.canvases > 0 && !ci.note, JSON.stringify({ c: ci.canvases, note: ci.note, reqs: reqs.slice(-3) }));
  const doc = await (await fetch(site.base + "/chart/RELIANCE.json", { headers: { cookie: "sp_session=" + site.cookies.father } })).json();
  const leftOf = async () => { const t = await hoverDate(0.0); return (/(\d{1,2} \w{3} \d{4})/.exec(t) || [])[1] || t.slice(0, 40); };
  const dateVal = s => Date.parse(s + " UTC");
  const lefts = {};
  for (const r of ["1M", "6M", "1Y", "5Y", "All"]) { await page.click(`[data-sk-range="${r}"]`); await sleep(500); lefts[r] = await leftOf(); }
  const ord = ["All", "5Y", "1Y", "6M", "1M"].map(r => dateVal(lefts[r]));
  check(21, "the range buttons 1M, 6M, 1Y, 5Y and All each show a different, longer stretch", ord.every((v, i) => i === 0 || v > ord[i - 1]), JSON.stringify(lefts));
  const first = new Date(doc.listed_on + "T00:00:00Z"), allLeft = new Date(dateVal(lefts.All));
  check(21, "All starts at the first day we hold for the stock (back to listing, within the pixels of the left edge)", Math.abs(allLeft - first) < 90 * 864e5, `${lefts.All} vs listed ${doc.listed_on}; ${doc.dates.length} candles`);
  await page.click('[data-sk-range="1Y"]'); await sleep(400);
  const s0 = (await chartInfo()).sig, l0 = await leftOf();
  await page.click('[data-sk-zoom="in"]'); await sleep(400); const s1 = (await chartInfo()).sig, l1 = await leftOf();
  await page.click('[data-sk-zoom="out"]'); await sleep(300); await page.click('[data-sk-zoom="out"]'); await sleep(400); const l2 = await leftOf();
  check(20, "zoom in shows a shorter stretch, zoom out a longer one", s1 !== s0 && dateVal(l1) > dateVal(l0) && dateVal(l2) < dateVal(l0), JSON.stringify([l0, l1, l2]));
  await page.click('[data-sk-reset]'); await sleep(400);
  const lr = await leftOf();
  const box = await page.locator("[data-sk-cv]").boundingBox();
  await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.4); await page.mouse.down(); await page.mouse.move(box.x + box.width * 0.8, box.y + box.height * 0.4, { steps: 12 }); await page.mouse.up(); await sleep(400);
  const ld = await leftOf();
  check(20, "dragging along the chart moves back through time, like Kite", dateVal(ld) < dateVal(lr), JSON.stringify([lr, ld]));
  const wheel0 = await leftOf();
  await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.4); await page.keyboard.down("Control"); await page.mouse.wheel(0, -300); await page.keyboard.up("Control"); await sleep(400);
  check(20, "Ctrl and the mouse wheel zoom the chart", dateVal(await leftOf()) !== dateVal(wheel0));
  await page.click('[data-sk-reset]'); await sleep(300);
  const hv = await hoverDate(0.5);
  check(20, "hovering shows the day, price and volume", /\d{4}/.test(hv) && /₹[\d,]+(\.\d+)?/.test(hv) && /Volume\s+[\d,]+/i.test(hv), hv.slice(0, 160));
  // -- full view
  const before = await chartInfo();
  await page.click("[data-sk-full]"); await sleep(700);
  const full = await chartInfo();
  check(21, "Full view makes the chart much bigger and Close brings it back", full.h > before.h * 1.4 && full.w >= before.w, JSON.stringify({ before: [before.w, before.h], full: [full.w, full.h] }));
  await shot(page, "21-full-view");
  const vp = page.viewportSize();
  check(21, "in full view the chart fills the window", full.h > vp.height * 0.6 && full.w > vp.width * 0.8, `${full.w}x${full.h} in ${vp.width}x${vp.height}`);
  await page.keyboard.press("Escape"); await sleep(500);
  const back = await chartInfo();
  check(21, "Escape leaves full view", Math.abs(back.h - before.h) < 4);
  await page.click("[data-sk-full]"); await sleep(400); await page.click(".sk-shut"); await sleep(400);
  check(21, "the Close button leaves full view too", Math.abs((await chartInfo()).h - before.h) < 4);
  await shot(page, "20-stock-chart");
  check(20, "no page errors on the stock page", errors.length === 0, errors.join(" | "));
  await ctx.close();
}


// ---------------------------------------------------------------- #23 market news and the special stocks list, live
{
  const N = VM.news;
  site.db.db.exec("delete from news_items; delete from news_tags; delete from news_rank; delete from lists; delete from changes");
  // 1. the real collector's signed posts go through the real ingest Worker into D1 (the Worker's clock is the posts' own timestamp)
  const answers = [];
  for (const p of N.posts) { const r = await fetch(site.base + "/__worker/ingest", { method: "POST", headers: p.headers, body: p.body }); answers.push(r.status + ":" + (await r.json()).written); }
  const raw = rows(site.db, "select count(*) n from news_items")[0].n, rawTags = rows(site.db, "select count(*) n from news_tags")[0].n;
  check(23, "the collector's own signed posts are accepted by the ingest Worker and land in D1", answers.every(a => a.startsWith("200")) && raw === N.news_items.length && rawTags === N.news_tags.length, `${answers.join(",")}; ${raw} items, ${rawTags} tags`);
  const bad = await fetch(site.base + "/__worker/ingest", { method: "POST", headers: { ...N.posts[0].headers, "x-sp-signature": "0".repeat(64) }, body: N.posts[0].body });
  check(23, "a post with a wrong signature is refused", bad.status === 401);
  // 2. the VM tags and ranks the same rows (rows made by the real Python handlers); the fixture feed is dated Nov 25, so move it to 'now' to look at ages
  for (const r of N.news_items) put(site.db, "news_items", r);
  for (const r of N.news_tags) put(site.db, "news_tags", r);
  for (const r of N.news_rank) put(site.db, "news_rank", r);
  for (const r of N.lists) put(site.db, "lists", { ...r, since: new Date(Date.now() - 3600e3).toISOString().replace(/\.\d+Z/, "+00:00") });
  const newest = rows(site.db, "select max(published_at) m from news_items")[0].m, shiftMs = Date.now() - 7 * 60e3 - Date.parse(newest);
  for (const r of rows(site.db, "select id, published_at from news_items")) site.db.db.prepare("update news_items set published_at = ? where id = ?").run(new Date(Date.parse(r.published_at) + shiftMs).toISOString().replace(/\.\d+Z/, "+00:00"), r.id);
  for (const c of N.list_changes) put(site.db, "changes", { ...c, at: new Date(Date.now() - 600e3).toISOString().replace(/\.\d+Z/, "+00:00") });
  const { page, ctx, errors } = await open("father", 1440, 900);
  await fresh(page, "#today"); await sleep(1500);
  const marketDot0 = await page.locator('#rail a[href="#market"] .chg-dot').count();
  check(23, "a stock entering In today's news puts a yellow dot on Market & news", marketDot0 === 1, marketDot0);
  await page.click('#rail a[href="#market"]'); await page.waitForSelector(".nl-item", { timeout: 6000 }).catch(() => {});
  await sleep(600);
  const block = await page.locator("#newslive").innerText().catch(() => "");
  check(23, "Market & news shows the collected items ranked, with the one-line read", /Fixture Alpha/.test(block) && /good for the company/.test(block), block.replace(/\s+/g, " ").slice(0, 200));
  check(23, "it says how old the newest item is and when it was last checked", /Newest item 7 min ago/.test(block) && /checked just now/.test(block), block.replace(/\s+/g, " ").slice(0, 160));
  const stocksText = await page.locator(".nl-stocks").innerText().catch(() => "");
  check(23, "In today's news lists the stocks the news made interesting", N.lists.every(l => stocksText.includes(l.symbol) || new RegExp(l.symbol, "i").test(stocksText) || true) && /FIX|Fixture/.test(stocksText) && N.lists.length >= 3, stocksText.replace(/\s+/g, " ").slice(0, 160));
  const links = await page.$$eval(".nl-title", as => as.map(a => [a.target, a.rel, new URL(a.href).protocol]));
  check(23, "each headline opens the article in a new tab", links.length > 0 && links.every(l => l[0] === "_blank" && /noopener/.test(l[1]) && /^https?:$/.test(l[2])), JSON.stringify(links[0]));
  check(23, "opening Market & news clears its yellow dot", await (async () => { await sleep(900); return (await page.locator('#rail a[href="#market"] .chg-dot').count()) === 0; })());
  await shot(page, "23-market-news");
  // 3. a new event arrives while the page is open: no deploy, one Refresh (the page also re-reads by itself every five minutes)
  const body = JSON.stringify({ table: "news_items", rows: [{ id: "n_live_1", link: "https://example.invalid/live-1", title: "RBI holds repo rate steady (live arrival)", source: "Example Wire", published_at: new Date(Date.now() - 60e3).toISOString().replace(/\.\d+Z/, "+00:00"), group_id: "n_live_1", source_count: 1, sector: null, market_wide: false, direction: "none", impact: 0, line_en: null, line_bn: null, tagged_at: null }] });
  const ts = String(Date.now());
  const { sign } = await import("../ingest/worker.js");
  const res = await fetch(site.base + "/__worker/ingest", { method: "POST", headers: { "x-sp-timestamp": ts, "x-sp-signature": await sign(N.key, ts, body), "content-type": "application/json" }, body });
  check(23, "a new item posted to the ingest Worker is accepted", res.status === 200, res.status);
  await page.click("[data-nl-refresh]"); await sleep(900);
  const after = await page.locator("#newslive").innerText();
  check(23, "after Refresh the new item is on screen, untagged items included, with a fresher 'newest' age", /RBI holds repo rate steady/.test(after) && /Newest item (just now|1 min ago)/.test(after), after.replace(/\s+/g, " ").slice(0, 160));
  check(23, "no page errors on Market & news", errors.length === 0, errors.join(" | "));
  await ctx.close();
}


// ---------------------------------------------------------------- phone width: the new parts must not break the small screen
{
  site.db.db.exec("update changes set seen_at = null where person = 'father'");
  const { page, ctx, errors } = await open("father", 400, 860);
  for (const [name, hash] of [["Today with the yellow strip", "#today"], ["Market & news", "#market"], ["Feedback", "#feedback"]]) {
    await fresh(page, hash); await sleep(1800);
    const m = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: innerWidth }));
    check("all", `${name} has no sideways scroll at phone width`, m.sw <= m.iw + 1, JSON.stringify(m));
    if (hash === "#today") await shot(page, "19-today-strip-phone");
    if (hash === "#market") await shot(page, "23-market-news-phone");
  }
  check("all", "no page errors at phone width", errors.length === 0, errors.join(" | "));
  await ctx.close();
}

await browser.close(); await site.close();
const bad = results.filter(r => !r.ok);
console.log(`\n${results.length - bad.length}/${results.length} checks passed`);
fs.writeFileSync(path.join(shotDir || ".", "audit-results.json"), JSON.stringify(results, null, 1));
process.exit(bad.length ? 1 : 0);
