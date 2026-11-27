import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import worker, { sign } from "../ingest/worker.js";
import { PUBLIC_TABLES, STOP_AT } from "../ingest/tables.js";

const KEY = "k".repeat(40);
const NOW = Date.parse("2026-11-25T09:15:00+05:30");
const contract = JSON.parse(readFileSync(new URL("../../schemas/live-contract.json", import.meta.url), "utf8"));

// Minimal in-memory D1: records writes, keeps the write_budget row.
function fakeDb(writes = 0) {
  const db = { budget: writes ? { day: "2026-11-25", writes } : null, inserted: [] };
  db.prepare = (sql) => ({
    sql, args: [],
    bind(...a) { this.args = a; return this; },
    async first() { return db.budget; },
    async run() { return this; },
  });
  db.batch = async (stmts) => {
    for (const s of stmts) {
      if (/^insert or replace into (\w+)/.test(s.sql)) db.inserted.push({ table: RegExp.$1, args: s.args });
      else if (/write_budget/.test(s.sql)) db.budget = { day: s.args[0], writes: s.args[1] };
    }
  };
  return db;
}
async function call(body, { db = fakeDb(), key = KEY, ts = NOW, sig, method = "POST" } = {}) {
  const raw = typeof body === "string" ? body : JSON.stringify(body);
  const headers = { "X-SP-Timestamp": String(ts) };
  headers["X-SP-Signature"] = sig ?? (await sign(key, ts, raw));
  const res = await worker.fetch(new Request("https://i.test/api/v2/ingest", { method, headers, body: method === "POST" ? raw : undefined }), { DB: db, INGEST_KEY: KEY }, { now: NOW });
  return { res, db, json: await res.json() };
}
const quote = { symbol: "FIXB", exchange: "NSE", price: 104.5, prev_close: 101, as_of: "2026-11-25T09:15:00+05:30", source: "yahoo" };

test("a signed write to a public table lands and the counter moves by row cost", async () => {
  const { res, db, json } = await call({ table: "quotes", rows: [quote] });
  assert.equal(res.status, 200);
  assert.deepEqual(json, { written: 1, writes_today: 1, stopped: false });
  assert.equal(db.inserted.length, 1);
  assert.equal(db.budget.writes, 1);
});

test("a write to a private table is refused", async () => {
  for (const table of ["calls", "lists", "jobs", "job_lines", "changes", "feedback", "asks", "news_rank", "write_budget", "sqlite_master"]) {
    const { res, db } = await call({ table, rows: [{ symbol: "X" }] });
    assert.equal(res.status, 403, table);
    assert.equal(db.inserted.length, 0, table);
  }
});

test("a request without a valid key is refused", async () => {
  const body = { table: "quotes", rows: [quote] };
  assert.equal((await call(body, { key: "w".repeat(40) })).res.status, 401, "wrong key");
  assert.equal((await call(body, { sig: "" })).res.status, 401, "empty signature");
  assert.equal((await call(body, { ts: NOW - 10 * 60 * 1000 })).res.status, 401, "stale timestamp (replay)");
  const raw = JSON.stringify(body);
  const sig = await sign(KEY, NOW, raw);
  const tampered = await call({ table: "quotes", rows: [{ ...quote, price: 1 }] }, { sig });
  assert.equal(tampered.res.status, 401, "body changed after signing");
  assert.equal(tampered.db.inserted.length, 0);
});

test("no INGEST_KEY configured means everything is refused", async () => {
  const res = await worker.fetch(new Request("https://i.test/", { method: "POST", body: "{}" }), { DB: fakeDb() }, { now: NOW });
  assert.equal(res.status, 401);
});

test("rows with unknown or missing columns are refused (no article text sneaks in)", async () => {
  assert.equal((await call({ table: "quotes", rows: [{ ...quote, body: "article text" }] })).res.status, 400);
  const { price, ...missing } = quote;
  assert.equal((await call({ table: "quotes", rows: [missing] })).res.status, 400);
  assert.equal((await call({ table: "quotes", rows: [] })).res.status, 400);
  assert.equal((await call("not json")).res.status, 400);
  assert.equal((await call({ table: "quotes", rows: Array(501).fill(quote) })).res.status, 400);
});

test("only POST is accepted", async () => {
  assert.equal((await call({}, { method: "GET" })).res.status, 405);
});

test("the budget counter stops writes before D1's daily limit", async () => {
  assert.ok(STOP_AT < contract.write_budget.daily_limit);
  assert.equal(STOP_AT, contract.write_budget.stop_at);
  const db = fakeDb(STOP_AT - 1);
  const { res, json } = await call({ table: "news_tags", rows: [{ item_id: "a", symbol: "FIXB", exchange: "NSE", relation: "self", direction: "good", size: "small", changes_call: false }] }, { db });
  assert.equal(res.status, 429); // cost 2 would pass STOP_AT
  assert.equal(json.stopped, true);
  assert.equal(db.inserted.length, 0);
  assert.equal(db.budget.writes, STOP_AT - 1, "counter untouched by a refused write");
  const again = await call({ table: "quotes", rows: [quote] }, { db: fakeDb(STOP_AT) });
  assert.equal(again.res.status, 429);
});

test("a write that exactly reaches the stop line is allowed, the next is not", async () => {
  const db = fakeDb(STOP_AT - 1);
  assert.equal((await call({ table: "quotes", rows: [quote] }, { db })).res.status, 200);
  assert.equal(db.budget.writes, STOP_AT);
  assert.equal((await call({ table: "quotes", rows: [quote] }, { db })).res.status, 429);
});

test("a new IST day starts the counter at zero", async () => {
  const db = fakeDb(STOP_AT);
  db.budget.day = "2026-11-24";
  const { res, json } = await call({ table: "quotes", rows: [quote] }, { db });
  assert.equal(res.status, 200);
  assert.equal(json.writes_today, 1);
});

test("tables.js matches the live contract", () => {
  const ingest = Object.entries(contract.tables).filter(([, t]) => t.writer === "ingest").filter(([n]) => n !== "write_budget");
  assert.deepEqual(Object.keys(PUBLIC_TABLES).sort(), ingest.map(([n]) => n).sort());
  for (const [name, t] of ingest) {
    assert.deepEqual(PUBLIC_TABLES[name].columns, Object.keys(t.columns), name);
    assert.equal(PUBLIC_TABLES[name].cost, 1 + t.indexes.length, name);
  }
  assert.equal(contract.write_budget.warn_at, 60000);
});
