// Test doubles for Pages Functions: a KV namespace, an env with secrets, and a runner that
// calls a handler the way Pages does (context.next() stands for "the route behind this one").
export const ORIGIN = "https://stockpilot.pages.dev";
export const COOKIE_KEY = "k".repeat(16) + "-test-cookie-key-0123456789";
export const VM_KEY = "vm-key-for-tests-0123456789abcdef";

export class FakeKV {
  constructor() { this.map = new Map(); this.puts = []; }
  async get(key, type) {
    const hit = this.map.get(key);
    if (!hit) return null;
    if (hit.expiration && hit.expiration * 1000 <= Date.now()) { this.map.delete(key); return null; }
    return type === "json" ? JSON.parse(hit.value) : hit.value;
  }
  async put(key, value, opts = {}) {
    if (opts.expiration !== undefined && opts.expiration * 1000 < Date.now() + 60_000) {
      throw new Error("KV expiration must be at least 60 seconds in the future");
    }
    this.puts.push({ key, value, opts });
    this.map.set(key, { value: String(value), expiration: opts.expiration });
  }
  async delete(key) { this.map.delete(key); }
}

// Two people, as in production (SP_PEOPLE, ADR 0006).
export const PEOPLE = { father: "father@example.test", owner: "owner@example.test" };
export const BRIDGE_URL = "https://script.google.test/macros/s/FAKE/exec";
export const BRIDGE_KEY = "bridge-key-for-tests";

export function makeEnv(overrides = {}) {
  return Object.assign({
    SP: new FakeKV(), SP_COOKIE_KEY: COOKIE_KEY, SP_VM_KEY: VM_KEY, SP_PEOPLE: JSON.stringify(PEOPLE),
    GOOGLE_BRIDGE_URL: BRIDGE_URL, GOOGLE_BRIDGE_KEY: BRIDGE_KEY,
  }, overrides);
}

// Replaces globalThis.fetch (via t.mock) with a fake Google bridge. It records each call.
export function fakeBridge(t, reply = () => ({ ok: true })) {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, init) => {
    const u = new URL(String(url));
    const call = { url: String(url), base: u.origin + u.pathname, params: Object.fromEntries(u.searchParams), init };
    calls.push(call);
    const out = await reply(call);
    if (out instanceof Response) return out;
    return new Response(JSON.stringify(out), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  return calls;
}

export function req(path, { method = "GET", headers = {}, body, ip = "203.0.113.7", origin } = {}) {
  const h = new Headers(headers);
  h.set("CF-Connecting-IP", ip);
  const unsafe = !["GET", "HEAD", "OPTIONS"].includes(method);
  if (origin !== undefined) { if (origin !== null) h.set("Origin", origin); }
  else if (unsafe) h.set("Origin", ORIGIN);
  return new Request(ORIGIN + path, { method, headers: h, body });
}

export function form(fields) {
  return { body: new URLSearchParams(fields).toString(), headers: { "Content-Type": "application/x-www-form-urlencoded" } };
}

// Runs one handler. `passed` says whether it called next(), i.e. let the request through.
export async function run(handler, request, env, data = {}) {
  let passed = false;
  const waits = [];
  const ctx = {
    request, env, data, params: {}, waitUntil(p) { waits.push(Promise.resolve(p)); },
    next: async () => { passed = true; return new Response("route body", { status: 200 }); },
  };
  const response = await handler(ctx);
  // settle() waits for the work handed to waitUntil, which Pages runs after the response is sent.
  return { response, passed, data, settle: () => Promise.all(waits) };
}

export function setCookieValue(response) {
  const raw = response.headers.get("Set-Cookie") || "";
  const m = raw.match(/(?:^|,\s*)sp_session=([^;]*)/);
  return m ? m[1] : null;
}
