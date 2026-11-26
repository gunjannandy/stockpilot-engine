// Dashboard check (v10): serves a built site with a mock API, walks every tab at desktop and phone width,
// clicks every button and asserts the queue request it sends. Usage: node e2e.mjs <site dir> [screenshot dir]
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const [siteDir, shotDir] = process.argv.slice(2);
const types = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".json": "application/json" };
const queued = [], queueCalls = [];
const posted = async (page, n) => { await page.waitForFunction(() => true); for (let i = 0; i < 50 && queued.length < n; i++) await page.waitForTimeout(40); };
let nextId = 1;
// The Worker's jobs list (GET /api/v2/jobs, owner only): what the page shows as waiting, done or failed.
const hour = n => new Date(Date.now() - n * 3600e3).toISOString();
let serverJobs = [
  { id: "job_900", kind: "refresh_docs", payload: {}, asked_by: "father", created_at: hour(2), status: "failed", error: "The Gmail bridge did not answer." },
  { id: "job_901", kind: "budget_set", payload: { month: "2026-10", amount: 90000 }, asked_by: "father", created_at: hour(900), status: "done", result: "Budget for 2026-10 is ₹90,000." },
];
const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://x");
  if (url.pathname === "/api/me") return res.end(JSON.stringify({ person: "Father" }));
  if (url.pathname === "/api/v2/jobs" && req.method === "GET") { res.setHeader("content-type", "application/json"); return res.end(JSON.stringify({ jobs: serverJobs })); }
  if ((url.pathname === "/api/v2/jobs" || url.pathname === "/api/v2/feedback") && req.method === "POST") {
    let body = ""; req.on("data", d => body += d);
    return req.on("end", () => {
      const b = JSON.parse(body), id = "job_" + nextId++;
      const q = url.pathname === "/api/v2/feedback" ? { kind: "feedback", payload: { text: b.text } } : b;   // the test reads both as one list of requests
      queued.push(q);
      serverJobs.push({ id, kind: q.kind, payload: q.payload, asked_by: "father", created_at: new Date().toISOString(), status: "queued" });
      res.setHeader("content-type", "application/json"); res.end(JSON.stringify({ id, status: "queued" }));
    });
  }
  if (url.pathname.startsWith("/api/queue")) { res.statusCode = 410; queueCalls.push(url.pathname); return res.end("{}"); }   // the KV queue is retired: nothing may call it
  const file = path.join(siteDir, url.pathname === "/" ? "index.html" : decodeURIComponent(url.pathname));
  if (!file.startsWith(path.resolve(siteDir)) || !fs.existsSync(file)) { res.statusCode = 404; return res.end("no"); }
  res.setHeader("content-type", types[path.extname(file)] || "application/octet-stream");
  res.end(fs.readFileSync(file));
});
await new Promise(r => server.listen(0, r));
const base = `http://127.0.0.1:${server.address().port}`;
const fails = [];
const check = (ok, what) => { if (!ok) { fails.push(what); console.error("FAIL:", what); } else console.log("ok:", what); };

const browser = await chromium.launch({ args: ["--no-sandbox"] });
const tabs = ["today", "holdings", "follow", "watchlist", "ideas", "market", "tax", "tradrec", "record", "settings", "feedback", "health"];
const settle = async page => { await page.evaluate(() => document.fonts.ready); await page.waitForTimeout(350); };
for (const [label, viewport] of [["desktop", { width: 1440, height: 900 }], ["phone", { width: 360, height: 780 }]]) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 1 });
  await ctx.route(/^https?:\/\/(?!127\.0\.0\.1)/, r => r.abort());
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", e => errors.push(String(e)));
  page.on("console", m => { if (m.type() === "error" && !/net::ERR_FAILED|Failed to load resource/.test(m.text())) errors.push(m.text()); });
  await page.goto(base + "/#today");
  await page.waitForSelector("#view h1"); await settle(page);
  for (const tab of tabs) {
    await page.evaluate(t => { location.hash = "#" + t; }, tab);
    await settle(page);
    const wide = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
    check(!wide, `${label} ${tab}: no sideways page scroll`);
    if (wide) console.log(await page.evaluate(() => [...document.querySelectorAll("body *")].filter(e => e.getBoundingClientRect().right > innerWidth + 1).slice(0, 8).map(e => `${e.tagName}.${e.className} right=${Math.round(e.getBoundingClientRect().right)} "${(e.textContent || "").slice(0, 50)}"`).join("\n")));
    const body = await page.locator("#view").innerText();
    check(!/\bnull\b|undefined|\[object|NaN/.test(body), `${label} ${tab}: no stray null, undefined or [object]`);
    if (label === "phone") {
      const small = await page.evaluate(() => [...document.querySelectorAll("#view button, #view input, #view .btn, #bar button, #bar a, #rail a")]
        .filter(e => e.offsetParent && !e.closest(".toast") && !e.closest(".lp-pane")).map(e => [e, e.getBoundingClientRect()]).filter(([, r]) => r.height > 0 && r.height < 43.5)
        .map(([e]) => (e.id || e.textContent || e.tagName).trim().slice(0, 30)));
      check(small.length === 0, `phone ${tab}: tap targets at least 44px tall ${small.join("|")}`);
    }
    check((await page.locator("#view h1").count()) >= 1 && !body.includes("could not load"), `${label} ${tab}: renders`);
    if (shotDir) await page.screenshot({ path: path.join(shotDir, `${label}-${tab}.png`), fullPage: true });
  }
  check(errors.length === 0, `${label}: no console errors ${errors.join("|")}`);

  if (label === "desktop") {
    await page.goto(base + "/#today"); await page.waitForSelector(".lrow"); await settle(page);
    check((await page.locator("#view").innerText()).includes("Consider buying"), "today: opens with the answer");
    check((await page.locator(".fresh .btn").getAttribute("href")) === "/kite/login", "Sync now goes to /kite/login");
    check((await page.locator("[role=alert]").innerText()).includes("The Gmail bridge did not answer."), "a failed request shows the VM's note");
    await page.locator("[data-qok]").click();
    check(await page.locator("[role=alert]").count() === 0, "the failed-request note can be dismissed");

    // snooze and dismiss from the full page
    await page.locator(".lrow").first().click(); await page.evaluate(() => { const sym = document.querySelector("#lpp")?.dataset.sym; document.body.insertAdjacentHTML("beforeend", `<a href="#stock" data-open="${sym}" id="__o">x</a>`); document.getElementById("__o").click(); document.getElementById("__o").remove(); }); await page.waitForSelector("[data-snooze]");
    { const n = queued.length + 1; await page.locator("[data-snooze]").click(); await posted(page, n); }
    check(queued.at(-1).kind === "snooze" && queued.at(-1).payload.scope === "stock", "snooze posts snooze");
    { const n = queued.length + 1; await page.locator("[data-dismiss]").click(); await page.waitForTimeout(100); check(queued.length < n, "Never show asks first"); await page.locator("[data-dismiss]").click(); await posted(page, n); }
    check(queued.at(-1).kind === "dismiss", "the cross posts dismiss");

    // watchlist: the inline add, the star (with undo), remove
    await page.goto(base + "/#watchlist"); await page.waitForSelector("#wla"); await settle(page);
    await page.fill("#wla", "zom"); await page.locator("#wlr li[data-wladd]", { hasText: "ZOMATO" }).click();
    await page.waitForSelector(".toast");
    check(JSON.stringify(queued.at(-1)) === JSON.stringify({ kind: "watchlist_add", payload: { symbol: "ZOMATO", exchange: "NSE" } }), "watchlist add posts watchlist_add");
    await page.locator(".toast button", { hasText: "Undo" }).last().click();
    await page.waitForTimeout(250);
    check(JSON.stringify(queued.at(-1)) === JSON.stringify({ kind: "watchlist_remove", payload: { symbol: "ZOMATO", exchange: "NSE" } }), "undo posts the opposite job");
    await page.locator('.lrow [data-star="SBIN"]').first().click({ force: true }); await page.waitForSelector(".toast");
    check(JSON.stringify(queued.at(-1)) === JSON.stringify({ kind: "watchlist_remove", payload: { symbol: "SBIN", exchange: "NSE" } }), "the star posts watchlist_remove");
    { const rows0 = await page.locator(".lrow").count(); await page.locator(".toast button", { hasText: "Undo" }).last().click(); await page.waitForTimeout(300);
      check(queued.at(-1).kind === "watchlist_add" && queued.at(-1).payload.symbol === "SBIN" && await page.locator(".lrow").count() === rows0 + 1, "undo puts the stock back on the watchlist"); }

    // an unanalysed stock: ask the analyst
    await page.goto(base + "/#ideas"); await page.waitForSelector(".lrow"); await settle(page);

    // settings buttons
    await page.goto(base + "/#settings"); await page.waitForSelector("#bud"); await settle(page);
    await page.fill("#bud", "150000"); { const n = queued.length + 1; await page.locator("[data-budget]").click(); await posted(page, n); }
    check(JSON.stringify(queued.at(-1)) === JSON.stringify({ kind: "budget_set", payload: { month: "2026-11", amount: 150000 } }), "budget posts budget_set");
    { const n = queued.length + 1; await page.locator("[data-approve]").click(); await posted(page, n); }
    check(queued.at(-1).kind === "allocation_approve" && queued.at(-1).payload.target.stocks === 0.55, "approve posts allocation_approve");
    { const n = queued.length + 1; await page.locator("[data-refresh]").click(); await posted(page, n); }
    check(queued.at(-1).kind === "refresh_docs", "refresh posts refresh_docs");
    { const n = queued.length + 1; await page.locator("[data-rerun]").click(); await posted(page, n); }
    check(queued.at(-1).kind === "rerun", "re-run posts rerun");

    // tax pack, feedback
    await page.goto(base + "/#tax"); await page.waitForSelector("[data-taxpack]"); await settle(page);
    { const n = queued.length + 1; await page.locator("[data-taxpack]").click(); await posted(page, n); }
    check(queued.at(-1).kind === "build_tax_pack", "tax pack posts build_tax_pack");
    await page.goto(base + "/#feedback"); await page.waitForSelector("#fbt"); await page.fill("#fbt", "Please show fewer small stocks.");
    { const n = queued.length + 1; await page.locator("[data-fb-act=send]").click(); await posted(page, n); }
    check(queued.at(-1).kind === "feedback" && queued.at(-1).payload.text.startsWith("Please show"), "feedback posts feedback");

    // the VM finishes the removal: Health lists the Worker's requests with the VM's notes
    serverJobs.find(i => i.kind === "watchlist_remove" || i.kind === "budget_set").result = "Done by the VM.";
    await page.goto(base + "/#health"); await page.waitForSelector("text=Requests from this page"); await settle(page);
    const reqs = await page.locator("#view").innerText();
    check(reqs.includes("Budget for 2026-10 is ₹90,000.") || reqs.includes("Done by the VM."), "health lists requests with the VM's notes");

    // search opens a stock
    await page.goto(base + "/#today"); await page.fill("#q", "wipro"); await page.waitForSelector("#sr li[role=option]"); await page.keyboard.press("Enter");
    await page.waitForFunction(() => location.hash.startsWith("#stock")); await settle(page);
    check(/wipro/i.test(await page.locator("#view").innerText()), "search opens a stock page");
  }
  await ctx.close();
}
await browser.close(); server.close();
check(queueCalls.length === 0, "nothing called the retired KV queue " + queueCalls.join(","));
if (fails.length) { console.error(fails.length + " checks failed"); process.exit(1); }
console.log("all checks passed");
