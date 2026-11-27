// Screenshots of every tab at desktop (1440x900) and phone (390x844), for design review.
// Usage: node shots.mjs <site dir> <out dir> [theme: light|dark]
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const [siteDir, outDir, theme = "light"] = process.argv.slice(2);
fs.mkdirSync(outDir, { recursive: true });
const types = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".json": "application/json" };
const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://x");
  if (url.pathname === "/api/me") return res.end(JSON.stringify({ person: "Father" }));
  if (url.pathname === "/api/queue") { res.setHeader("content-type", "application/json"); return res.end(JSON.stringify({ items: [] })); }
  const file = path.join(siteDir, url.pathname === "/" ? "index.html" : decodeURIComponent(url.pathname));
  if (!fs.existsSync(file)) { res.statusCode = 404; return res.end("no"); }
  res.setHeader("content-type", types[path.extname(file)] || "application/octet-stream");
  res.end(fs.readFileSync(file));
});
await new Promise(r => server.listen(0, r));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ args: ["--no-sandbox"] });
const tabs = ["today", "market", "ideas", "watchlist", "lookup/INFY", "portfolio", "record", "health"];
for (const [label, viewport] of [["desktop", { width: 1440, height: 900 }], ["phone", { width: 360, height: 780 }]]) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 1, colorScheme: theme });
  await ctx.route(/^https?:\/\/(?!127\.0\.0\.1)/, r => r.abort());
  const page = await ctx.newPage();
  await page.goto(base + "/#today"); await page.waitForSelector("h1");
  for (const tab of tabs) {
    await page.evaluate(t => { location.hash = "#" + t; }, tab);
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(outDir, `${label}-${tab.replace("/", "-")}.png`), fullPage: true });
  }
  await ctx.close();
}
await browser.close(); server.close();
