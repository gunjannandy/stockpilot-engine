// Pure helpers for the cutover tooling (ticket V4). No I/O, so the tests need no network.

// KEY=VALUE lines of a .env file. Quotes are stripped; comments and lines without "=" are skipped.
export function parseDotenv(text) {
  const out = {};
  for (const raw of String(text).split(/\r?\n/)) {
    const line = raw.trim().replace(/^export\s+/, "");
    if (!line || line.startsWith("#")) continue;
    const m = /^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/.exec(line);
    if (!m) continue;
    let v = m[2].trim();
    if (/^(".*"|'.*')$/.test(v)) v = v.slice(1, -1);
    out[m[1]] = v;
  }
  return out;
}

// The deployment URL that `wrangler pages deploy` prints.
export function parseDeployUrl(output) {
  const m = /https:\/\/[a-z0-9-]+\.[a-z0-9-]+\.pages\.dev/i.exec(String(output));
  return m ? m[0] : null;
}

// The page's own number formatting (web/public/app.js: inr, px, pct), so "on screen" strings can be rebuilt from the data.
export const inr = (v, d = 0) => v == null ? "–" : "₹" + Number(v).toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d });
export const px = (v) => v == null ? "–" : inr(v, v < 100 ? 2 : v < 1000 ? 1 : 0);
export const pct = (v) => v == null ? "–" : (v * 100).toFixed(0) + "%";

// Rows are what the browser read from the Today list (`.lrow[data-sel="today:SYMBOL"]`): [{sym, text}] with the row's text.
// today is data/today.json. Every buy and sell in the data must be a row, and the row must show the data's numbers:
// the chance, and for a buy the target price, for a sell the worth of the shares (quantity x entry).
export function compareToday(rows, today) {
  const mismatches = [];
  const bySym = new Map((rows || []).map((r) => [r.sym, r]));
  const items = [...(today?.buy || []), ...(today?.sell || [])];
  const isSell = new Set((today?.sell || []).map((x) => x.symbol));
  for (const it of items) {
    const row = bySym.get(it.symbol);
    if (!row) { mismatches.push(`${it.symbol}: in today.json but not on screen`); continue; }
    const want = [["chance", pct(it.probability)]];
    if (isSell.has(it.symbol)) { if (it.quantity && it.entry) want.push(["worth", inr(it.quantity * it.entry)]); }
    else if (it.target) want.push(["target price", px(it.target)]);
    for (const [label, text] of want) if (!row.text.includes(text)) mismatches.push(`${it.symbol}: ${label} on screen is not ${text} (the data)`);
  }
  return { checked: items.length, mismatches };
}

// The four hard blocks (docs/status/orchestration-decisions.md section 3). `r` is what one browser pass saw.
export function verdict(r) {
  const failed = [];
  if (!r.loaded || r.gate) failed.push("page_loads");
  if ((r.pageErrors || []).length) failed.push("js_page_error");
  const emptyOk = r.expectedRows === 0 && r.nothingLine;      // "Nothing to do today" is a valid call, but only when the data says so
  if (r.loaded && !r.gate && !(r.rows > 0 || emptyOk)) failed.push("today_not_empty");
  if ((r.mismatches || []).length) failed.push("numbers_match");
  return { ok: failed.length === 0, failed };
}
