// One simulated night of D1 writes, with synthetic rows only (no real tickers, holdings or amounts).
// Table shapes are the probe's own guess at the T0 contract: small, changing rows.
export const D1_FREE_WRITES_PER_DAY = 100_000;

export const SCHEMA = [
  "CREATE TABLE stock_state (symbol TEXT PRIMARY KEY, call TEXT, chance_pct INTEGER, updated_at INTEGER)",
  "CREATE INDEX stock_state_updated ON stock_state(updated_at)",
  "CREATE TABLE news_item (id TEXT PRIMARY KEY, link TEXT, title TEXT, source TEXT, published_at INTEGER, tags TEXT)",
  "CREATE INDEX news_item_time ON news_item(published_at)",
  "CREATE TABLE forecast (symbol TEXT PRIMARY KEY, form TEXT, made_at INTEGER)",
];

const NOW = 1_800_000_000;

export function nightStatements({ stocks, newsItems, forecasts }) {
  const out = [];
  for (let i = 0; i < stocks; i++) {
    out.push({
      sql: "INSERT OR REPLACE INTO stock_state (symbol, call, chance_pct, updated_at) VALUES (?, ?, ?, ?)",
      args: [`SYN${i}`, i % 3 ? "Hold" : "Buy", 40 + (i % 30), NOW],
    });
  }
  for (let i = 0; i < newsItems; i++) {
    out.push({
      sql: "INSERT OR REPLACE INTO news_item (id, link, title, source, published_at, tags) VALUES (?, ?, ?, ?, ?, ?)",
      args: [`n${i}`, `https://news.example/${i}`, `Synthetic headline ${i}`, "example", NOW + i, JSON.stringify({ stocks: [`SYN${i % stocks}`], impact: "low" })],
    });
  }
  for (let i = 0; i < forecasts; i++) {
    out.push({
      sql: "INSERT OR REPLACE INTO forecast (symbol, form, made_at) VALUES (?, ?, ?)",
      args: [`SYN${i}`, "x".repeat(4000), NOW],
    });
  }
  return out;
}
