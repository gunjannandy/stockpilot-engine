// Login primitives for the dashboard (ADR 0005 for the cookie, ADR 0006 for the emailed link).
// WebCrypto only, so the same code runs in Cloudflare Pages Functions and in Node tests.
//
// Secrets (Pages secrets, never in git):
//   SP_PEOPLE            JSON {"owner": "<email>", "father": "<email>"}: who may sign in, and where the link goes
//   SP_COOKIE_KEY        random, 32+ characters; rotating it signs everybody out
//   SP_VM_KEY            random, 16+ characters; the VM sends it as X-SP-Key
//   GOOGLE_BRIDGE_URL, GOOGLE_BRIDGE_KEY   the Apps Script bridge that sends the email
// KV binding SP holds the single-use links (link:<sha256 of token>) and the rate-limit counters.

export const COOKIE = "sp_session";
export const SESSION_SECONDS = 365 * 24 * 60 * 60;
export const LINK_SECONDS = 15 * 60;
const MIN_COOKIE_KEY = 32;
const MIN_VM_KEY = 16;
export const PERSON_LIMIT = 3, PERSON_WINDOW_SECONDS = 15 * 60;
export const IP_LIMIT = 10, IP_WINDOW_SECONDS = 60 * 60;
const PERSON = /^[a-z0-9_]{1,32}$/;

const enc = new TextEncoder();

function b64url(bytes) {
  let s = "";
  for (const b of new Uint8Array(bytes)) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function unb64url(text) {
  if (typeof text !== "string" || !/^[A-Za-z0-9_-]+$/.test(text)) return null;
  try {
    const bin = atob(text.replace(/-/g, "+").replace(/_/g, "/"));
    return Uint8Array.from(bin, (c) => c.charCodeAt(0));
  } catch { return null; }
}

function equalBytes(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
  return diff === 0;
}

const EMAIL = /^[^\s@,&?=<>"'#%+]+@[^\s@,&?=<>"'#%+]+\.[^\s@,&?=<>"'#%+]+$/;

// People are the keys of the SP_PEOPLE secret. Bad entries are dropped, never trusted.
export function people(env) {
  let parsed;
  try { parsed = JSON.parse(env?.SP_PEOPLE); } catch { return {}; }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
  const out = {};
  for (const [id, email] of Object.entries(parsed)) {
    if (id !== "__proto__" && PERSON.test(id) && typeof email === "string" && EMAIL.test(email.trim())) out[id] = email.trim();
  }
  // v1 stored two legacy ids; v2 expects "owner" and "father". With SP_OWNER naming one of exactly two
  // people and no "owner" key, that person is "owner" and the other is "father".
  const ids = Object.keys(out), legacyOwner = env?.SP_OWNER;
  if (typeof legacyOwner === "string" && ids.length === 2 && !Object.hasOwn(out, "owner") && Object.hasOwn(out, legacyOwner)) {
    const other = ids.find((id) => id !== legacyOwner);
    return { owner: out[legacyOwner], father: out[other] };
  }
  return out;
}

export const knownPerson = (env, id) => typeof id === "string" && Object.hasOwn(people(env), id);

// The person whose address is `email` (already trimmed and lower-cased), or null. Every entry is
// compared with the same constant-time check and none is skipped, so the time does not say which matched.
export async function personForEmail(env, email) {
  const set = people(env);
  let found = null;
  for (const [id, address] of Object.entries(set)) {
    if (await sameSecret(email, address.toLowerCase())) found = id;
  }
  return found;
}

// Used by /api/me only; the sign-in page never shows a name.
export function displayName(person) {
  return person ? person[0].toUpperCase() + person.slice(1) : "";
}

export function newToken() {
  return b64url(crypto.getRandomValues(new Uint8Array(32)));
}

export async function sha256hex(text) {
  return [...new Uint8Array(await crypto.subtle.digest("SHA-256", enc.encode(text)))].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export const TOKEN = /^[A-Za-z0-9_-]{43}$/;
export const linkKey = async (token) => `link:${await sha256hex(token)}`;

async function hmacKey(secret) {
  return crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);
}

// Session value: v1.<person>.<expires, unix seconds>.<HMAC-SHA256 of the first three parts>
export async function signSession(person, secret, now = Date.now()) {
  if (typeof secret !== "string" || secret.length < MIN_COOKIE_KEY) throw new Error("SP_COOKIE_KEY is missing or shorter than 32 characters");
  if (!PERSON.test(person)) throw new Error("bad person id");
  const body = `v1.${person}.${Math.floor(now / 1000) + SESSION_SECONDS}`;
  return `${body}.${b64url(await crypto.subtle.sign("HMAC", await hmacKey(secret), enc.encode(body)))}`;
}

export async function verifySession(value, secret, now = Date.now()) {
  if (typeof secret !== "string" || secret.length < MIN_COOKIE_KEY || typeof value !== "string") return null;
  const parts = value.split(".");
  if (parts.length !== 4 || parts[0] !== "v1" || !PERSON.test(parts[1]) || !/^\d{1,12}$/.test(parts[2])) return null;
  const sig = unb64url(parts[3]);
  if (!sig || sig.length !== 32) return null;
  // crypto.subtle.verify compares in constant time.
  const ok = await crypto.subtle.verify("HMAC", await hmacKey(secret), sig, enc.encode(parts.slice(0, 3).join(".")));
  if (!ok) return null;
  const expires = Number(parts[2]), nowSec = Math.floor(now / 1000);
  if (expires <= nowSec || expires > nowSec + SESSION_SECONDS + 60) return null;
  return parts[1];
}

// Constant-time equality for two secrets of any length: compare their SHA-256 digests.
export async function sameSecret(given, expected) {
  if (typeof given !== "string" || typeof expected !== "string" || !given || !expected) return false;
  const [a, b] = await Promise.all([given, expected].map(async (s) => new Uint8Array(await crypto.subtle.digest("SHA-256", enc.encode(s)))));
  return equalBytes(a, b);
}

export function vmKeyUsable(key) {
  return typeof key === "string" && key.length >= MIN_VM_KEY;
}

export function cookieKeyUsable(key) {
  return typeof key === "string" && key.length >= MIN_COOKIE_KEY;
}

export function readCookie(request, name = COOKIE) {
  for (const part of (request.headers.get("Cookie") || "").split(";")) {
    const i = part.indexOf("=");
    if (i > 0 && part.slice(0, i).trim() === name) return part.slice(i + 1).trim();
  }
  return null;
}

export async function sessionPerson(request, env) {
  if (!cookieKeyUsable(env?.SP_COOKIE_KEY)) return null;
  const person = await verifySession(readCookie(request), env.SP_COOKIE_KEY, Date.now());
  // A person who is no longer in SP_PEOPLE is signed out.
  return person && knownPerson(env, person) ? person : null;
}

export function sessionCookie(value) {
  return `${COOKIE}=${value}; Max-Age=${SESSION_SECONDS}; Path=/; HttpOnly; Secure; SameSite=Lax`;
}

export function clearedCookie() {
  return `${COOKIE}=; Max-Age=0; Path=/; HttpOnly; Secure; SameSite=Lax`;
}

// Where to go after login: only a path on this site, never back to /login.
export function safeNext(next) {
  if (typeof next !== "string" || next.length > 2048 || !next.startsWith("/")) return "/";
  if (next.startsWith("//") || next.includes("\\") || /[\u0000-\u001f\u007f]/.test(next)) return "/";
  const path = next.split(/[?#]/)[0].toLowerCase();
  if (path === "/login" || path.startsWith("/login/")) return "/";
  return next;
}

// Rate limits in KV: a counter that starts at the first request and runs for its window. KV is
// eventually consistent, so a burst from many edge locations can slip a few extra through.
export async function waitFor(kv, key, limit) {
  const rec = await kv.get(key, "json");
  const nowSec = Math.floor(Date.now() / 1000);
  if (!rec || rec.until <= nowSec || rec.n < limit) return 0;
  return rec.until - nowSec;
}

export async function record(kv, key, windowSeconds) {
  const nowSec = Math.floor(Date.now() / 1000);
  let rec = await kv.get(key, "json");
  if (!rec || rec.until <= nowSec) rec = { n: 0, until: nowSec + windowSeconds };
  rec.n += 1;
  await kv.put(key, JSON.stringify(rec), { expiration: Math.max(rec.until, nowSec + 61) });
}

// Public jobs write news and quotes with their own write-only key, sent as X-SP-Ingest-Key.
export async function ingestAllowed(request, env) {
  return typeof env?.SP_INGEST_KEY === "string" && env.SP_INGEST_KEY.length >= 16 && (await sameSecret(request.headers.get("X-SP-Ingest-Key"), env.SP_INGEST_KEY));
}

