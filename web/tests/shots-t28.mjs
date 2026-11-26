// T28 screenshots: Jobs, Health, Settings at 1440, 1100 and 400, light and dark, on invented data.
// Usage: node web/tests/shots-t28.mjs <out dir>
import http from "node:http"; import fs from "node:fs"; import path from "node:path"; import { createRequire } from "node:module";
const { chromium } = createRequire(import.meta.url)("playwright");
const out = process.argv[2]; fs.mkdirSync(out, { recursive: true });
const pub = new URL("../public/", import.meta.url).pathname;
const kinds = ["sync", "analyse", "refresh_call", "feedback_read", "news_tag", "news_rank", "load_stock", "news_collect", "history_backfill", "nightly", "weekly_review", "backup"];
const iso = m => new Date(Date.now() - m * 60000 + 330 * 60000).toISOString().replace("Z", "+05:30").replace(/\.\d+/, "");
const J = (i, kind, status, ago, took, extra = {}) => ({ id: "j" + i, kind, payload: kind === "analyse" || kind === "refresh_call" ? { symbol: "FIXA", exchange: "NSE" } : {}, asked_by: ["owner", "father", "system"][i % 3], status, result: status === "done" ? "Done, 3 changes" : null, error: status === "failed" ? "No model is available. Usage is used up; try again in about an hour." : null, error_bn: null, created_at: iso(ago), started_at: status === "queued" ? null : iso(ago), finished_at: status === "done" || status === "failed" ? iso(ago - took) : null, ...extra });
const jobs = [J(1, "analyse", "running", 4), J(2, "nightly", "running", 11), J(3, "backup", "queued", 1), J(4, "news_collect", "done", 14, 1), J(5, "refresh_call", "failed", 36, 1), J(6, "sync", "done", 55, 2), ...kinds.slice(3, 12).map((k, i) => J(10 + i, k, i % 5 === 4 ? "failed" : "done", 90 + i * 20, 3 + i))];
const lines = id => [{ seq: 1, at: iso(5), state: "ok", text: "Queued", text_bn: null }, { seq: 2, at: iso(4), state: "ok", text: "Fetched prices", text_bn: null }, { seq: 3, at: iso(2), state: "info", text: "Mechanical forecast", text_bn: null }];
const health = { headline: "Everything is working.", runs: [], problems: [], gaps: [{ what: "Promoter holding", reason: "Source down" }], needs: [], freshness: [{ name: "Prices", when: "2026-11-25 09:00", days_old: 0 }, { name: "Holdings", when: "2026-11-24 09:00", days_old: 1 }, { name: "Documents", when: "2026-11-20 09:00", days_old: 5 }], tokens: [{ name: "Zerodha login", days_left: 1 }, { name: "Model access", days_left: 40 }] };
health.runs = Array.from({ length: 14 }, (_, i) => ({ job: i % 2 ? "Nightly forecasts" : "News refresh", started_at: `2026-11-${10 + i} 02:00:00`, finished_at: `2026-11-${10 + i} 02:${10 + i}:00`, status: i === 5 ? "failed" : "ok", error: i === 5 ? "Source timed out" : null }));
const types = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".json": "application/json" };
const send = (res, b) => { res.setHeader("content-type", "application/json"); res.end(JSON.stringify(b)); };
const server = http.createServer((req, res) => {
  const u = new URL(req.url, "http://x"), p = u.pathname;
  if (p === "/api/me") return send(res, { person: "owner" });
  if (p === "/api/queue") return send(res, { items: [] });
  if (p === "/api/v2/jobs") return send(res, { jobs });
  if (p === "/api/v2/budget") return send(res, { day: "2026-11-25", writes: 18000, warn_at: 60000, stop_at: 85000, status: "ok" });
  if (p.startsWith("/api/v2/jobs/")) return send(res, { job: jobs[0], lines: lines() });
  if (p.startsWith("/api/v2/")) return send(res, { items: [], quotes: [] });
  if (p === "/data/health.json") return send(res, health);
  if (p === "/data/settings.json") return send(res, { budget: { total: 500000, left: 320000, month: "2026-11" } });
  if (p === "/data/meta.json") return send(res, { built_at: "2026-11-25T09:50:00", status: { text: "Everything is up to date." } });
  const f = path.join(pub, p === "/" ? "index.html" : decodeURIComponent(p));
  if (!fs.existsSync(f) || fs.statSync(f).isDirectory()) { res.statusCode = 404; return res.end("no"); }
  res.setHeader("content-type", types[path.extname(f)] || "application/octet-stream"); res.end(fs.readFileSync(f));
});
await new Promise(r => server.listen(0, r));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ args: ["--no-sandbox"] });
const errors = [];
for (const theme of ["light", "dark"]) for (const w of [1440, 1100, 400]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: w === 400 ? 800 : 900 }, deviceScaleFactor: 1, colorScheme: theme });
  await ctx.route(/^https?:\/\/(?!127\.0\.0\.1)/, r => r.abort());
  const page = await ctx.newPage(); page.on("pageerror", e => errors.push(e.message));
  await page.goto(base + "/#jobs"); await page.waitForSelector("h1");
  for (const tab of ["jobs", "health", "settings"]) {
    await page.evaluate(t => { location.hash = "#" + t; }, tab); await page.waitForTimeout(900);
    const over = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
    if (over > 1) errors.push(`${tab} ${w} ${theme}: sideways overflow ${over}px`);
    await page.screenshot({ path: path.join(out, `${tab}-${w}-${theme}.png`), fullPage: tab === "jobs" });
  }
  await ctx.close();
}
await browser.close(); server.close();
console.log(errors.length ? errors.join("\n") : "no page errors, no sideways overflow");
