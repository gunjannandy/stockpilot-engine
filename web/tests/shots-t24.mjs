// T24 screenshots of Worth following with fixture data (made-up symbols) at 1440, 1100 and 400, light and dark.
// Usage: node tests/shots-t24.mjs <out dir>
import http from "node:http"; import fs from "node:fs"; import path from "node:path";
import { createRequire } from "node:module";
const { chromium } = createRequire(import.meta.url)("playwright");
const out = process.argv[2] || "../docs/screenshots/t24"; fs.mkdirSync(out, { recursive: true });
const pub = new URL("../public/", import.meta.url).pathname, fxd = new URL("../../tests/fixtures/live/", import.meta.url).pathname;
const types = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".json": "application/json" };
const name = { FIXA: "Fixture Alpha Ltd", FIXB: "Fixture Bravo Ltd", FIXC: "Fixture Charlie SME", FIXD: "Fixture Delta Ltd", FIXE: "Fixture Echo Ltd", FIXH: "Fixture Held Ltd" };
const items = [["FIXA", "NSE", "buy", .64, "Strong growth and a fair price"], ["FIXB", "NSE", "wait", .55, "Profit up 24%, price near its 50-day average"], ["FIXC", "BSE", "buy", .59, "SME stock with fast growth; thin trading", true],
  ["FIXD", "NSE", null, null, "No forecast yet"], ["FIXE", "BSE", "hold", .36, "Cheap against its sector but a small company"], ["FIXH", "NSE", "buy", .7, "Held stock, must not show"]]
  .map(([symbol, exchange, call, chance_3m, reason, ood], i) => ({ symbol, exchange, rank: i + 1, reason, reason_bn: null, since: "2026-11-25T09:15:00+05:30", call, chance_3m, out_of_date: !!ood }));
let job = null, step = 0;
const json = (res, b, code = 200) => { res.statusCode = code; res.setHeader("content-type", "application/json"); res.end(JSON.stringify(b)); };
const server = http.createServer((req, res) => {
  const u = new URL(req.url, "http://x"), p = u.pathname;
  if (p === "/api/me") return json(res, { person: "father" });
  if (p === "/api/queue") return json(res, { items: [], id: "q1" });
  if (p === "/api/v2/lists/worth_following") return json(res, { list_name: "worth_following", items: items.map(i => i.symbol === "FIXD" && job === "done" ? { ...i, call: "buy", chance_3m: .6, reason: "Analysed just now" } : i) });
  if (p === "/api/v2/jobs" && req.method === "POST") { job = "running"; step = 0; return json(res, { id: "job_1", status: "queued" }); }
  if (p === "/api/v2/jobs/job_1") { step++; if (step > 3) job = "done";
    const lines = ["Reading the numbers", "Reading the news", "Writing the forecast"].slice(0, Math.min(step, 3)).map((text, k) => ({ job_id: "job_1", seq: k + 1, at: "2026-11-25T09:15:00+05:30", state: "info", text, text_bn: null }));
    return json(res, { job: { id: "job_1", kind: "analyse", payload: {}, asked_by: "father", status: job, result: job === "done" ? "Done, 1 change" : null, error: null, error_bn: null, created_at: "", started_at: "", finished_at: null }, lines }); }
  if (p.startsWith("/api/v2/")) return json(res, { items: [], quotes: [], person: "father" });
  if (p === "/data/portfolio.json") return json(res, { holdings: [{ symbol: "FIXH", name: "Fixture Held Ltd", quantity: 10, value: 10000 }] });
  if (p === "/search/index.json") return json(res, { entries: Object.entries(name).map(([symbol, n]) => ({ symbol, name: n, exchange: "NSE" })) });
  const f = path.join(pub, p === "/" ? "index.html" : decodeURIComponent(p));
  if (!fs.existsSync(f) || fs.statSync(f).isDirectory()) { res.statusCode = 404; return res.end("no"); }
  res.setHeader("content-type", types[path.extname(f)] || "application/octet-stream"); res.end(fs.readFileSync(f));
});
await new Promise(r => server.listen(0, r)); const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ args: ["--no-sandbox"] });
for (const theme of ["light", "dark"]) for (const w of [1440, 1100, 400]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: w === 400 ? 800 : 900 }, deviceScaleFactor: 1, colorScheme: theme });
  const page = await ctx.newPage(); job = null;
  page.on("console", m => m.type() === "error" && console.log("CONSOLE", m.text().slice(0, 150))); page.on("pageerror", e => console.log("PAGEERROR", e.stack.split("\n").slice(0,4).join(" | ")));
  await page.goto(base + "/#follow"); await page.waitForSelector(".wf-row", { timeout: 8000 }).catch(async () => { console.log((await page.innerText("body")).slice(0, 400)); throw new Error("no rows"); });
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(out, `worth-${w}-${theme}.png`) });
  if (theme === "light" && w === 1440) {
    console.log("rows", await page.$$eval(".wf-row", r => r.map(x => x.dataset.sym)));
    await page.click('[data-analyse="FIXD"]'); await page.waitForTimeout(1200);
    await page.screenshot({ path: path.join(out, "worth-1440-light-analysing.png") });
    await page.waitForTimeout(9000);
    console.log("after", await page.$$eval(".wf-row", r => r.map(x => x.dataset.sym + ":" + (x.querySelector(".wf-p")?.textContent || "-"))));
    await page.click('[data-snooze="FIXB"]'); await page.waitForTimeout(300);
    console.log("snoozed", await page.$$eval(".wf-row", r => r.map(x => x.dataset.sym)));
  }
  await ctx.close();
}
await browser.close(); server.close();
