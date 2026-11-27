// Write-only ingest Worker (ticket T12, spec #24 decision D3).
// Public jobs (GitHub Actions in stockpilot-engine) hold only INGEST_KEY, never a Cloudflare token.
// They POST {table, rows} signed with HMAC-SHA256 over "<timestamp>.<raw body>".
// Accepts only the public tables in tables.js. Keeps the daily write counter in D1's write_budget
// and refuses writes that would pass STOP_AT, so the owners' own button presses keep their room.
//
// Secrets and bindings (Worker secrets, never in git): INGEST_KEY (32+ chars), DB (D1).
import { PUBLIC_TABLES, WARN_AT, STOP_AT } from "./tables.js";

const MAX_ROWS = 500;
const MAX_SKEW_MS = 5 * 60 * 1000;
const MIN_KEY = 32;
const enc = new TextEncoder();
const reply = (body, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });

const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");

async function hmacKey(secret) {
  return crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);
}

// Signature the caller must send in X-SP-Signature (hex), with X-SP-Timestamp in epoch milliseconds.
export async function sign(secret, timestamp, rawBody) {
  return hex(await crypto.subtle.sign("HMAC", await hmacKey(secret), enc.encode(`${timestamp}.${rawBody}`)));
}

async function validSignature(env, request, raw, now) {
  const key = env.INGEST_KEY;
  if (typeof key !== "string" || key.length < MIN_KEY) return false;
  const ts = Number(request.headers.get("X-SP-Timestamp"));
  const given = request.headers.get("X-SP-Signature") || "";
  if (!Number.isFinite(ts) || Math.abs(now - ts) > MAX_SKEW_MS || !/^[0-9a-f]{64}$/.test(given)) return false;
  const bytes = Uint8Array.from(given.match(/../g), (h) => parseInt(h, 16));
  // crypto.subtle.verify compares in constant time.
  return crypto.subtle.verify("HMAC", await hmacKey(key), bytes, enc.encode(`${ts}.${raw}`));
}

// IST calendar day (D1's budget resets on this boundary for our purposes; the counter is ours).
const istDay = (ms) => new Date(ms + 5.5 * 3600 * 1000).toISOString().slice(0, 10);

function rowsOk(spec, rows) {
  if (!Array.isArray(rows) || rows.length === 0 || rows.length > MAX_ROWS) return false;
  const want = [...spec.columns].sort().join(",");
  return rows.every((r) => r && typeof r === "object" && !Array.isArray(r) && Object.keys(r).sort().join(",") === want);
}

const bindable = (v) => (v === undefined ? null : typeof v === "boolean" ? (v ? 1 : 0) : typeof v === "object" && v !== null ? JSON.stringify(v) : v);

export default {
  async fetch(request, env, ctx = {}) {
    const now = ctx.now ?? Date.now();
    if (request.method !== "POST") return reply({ error: "POST only" }, 405);
    const raw = await request.text();
    if (!(await validSignature(env, request, raw, now))) return reply({ error: "bad key" }, 401);

    let body;
    try { body = JSON.parse(raw); } catch { return reply({ error: "bad json" }, 400); }
    if (!body || typeof body !== "object" || Array.isArray(body)) return reply({ error: "bad body" }, 400);
    const spec = Object.hasOwn(PUBLIC_TABLES, body.table) ? PUBLIC_TABLES[body.table] : null;
    if (!spec) return reply({ error: "table not allowed" }, 403);
    if (!rowsOk(spec, body.rows)) return reply({ error: "bad rows" }, 400);

    const day = istDay(now);
    const saved = await env.DB.prepare("select day, writes from write_budget where day = ?").bind(day).first();
    const before = saved && saved.day === day ? saved.writes : 0;
    const cost = body.rows.length * spec.cost;
    if (before + cost > STOP_AT) return reply({ error: "daily write budget reached", writes_today: before, stopped: true }, 429);

    const cols = spec.columns;
    const insert = `insert or replace into ${body.table} (${cols.join(",")}) values (${cols.map(() => "?").join(",")})`;
    const after = before + cost;
    const stamp = new Date(now + 5.5 * 3600 * 1000).toISOString().slice(0, 19) + "+05:30";
    await env.DB.batch([
      ...body.rows.map((r) => env.DB.prepare(insert).bind(...cols.map((c) => bindable(r[c])))),
      env.DB.prepare(
        "insert into write_budget (day, writes, warn_at, stop_at, updated_at) values (?, ?, ?, ?, ?) " +
        "on conflict(day) do update set writes = excluded.writes, updated_at = excluded.updated_at",
      ).bind(day, after, WARN_AT, STOP_AT, stamp),
    ]);
    return reply({ written: body.rows.length, writes_today: after, stopped: after >= STOP_AT });
  },
};
