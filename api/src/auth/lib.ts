// Sign-in primitives (ADR 0005 for the cookie, ADR 0006 for the emailed link), WebCrypto only.
//
// Secrets (Worker secrets, never in git):
//   SP_PEOPLE              JSON {"owner": "<email>", "father": "<email>"}: who may sign in, and where the link goes
//   SP_COOKIE_KEY          32+ characters, signs production sessions; rotating it signs everybody out
//   SP_PREVIEW_COOKIE_KEY  32+ characters, a different secret that signs preview sessions
//   SP_ENV                 "preview" on previews; anything else (or unset) is production
//   GOOGLE_BRIDGE_URL, GOOGLE_BRIDGE_KEY   the Apps Script send endpoint
import type { Context } from "hono";
import type { Ctx } from "../app";

export type AuthEnv = {
  SP_PEOPLE?: string;
  SP_COOKIE_KEY?: string;
  SP_PREVIEW_COOKIE_KEY?: string;
  SP_ENV?: string;
  SITE_URL?: string;
  GOOGLE_BRIDGE_URL?: string;
  GOOGLE_BRIDGE_KEY?: string;
  ASSETS?: { fetch(req: Request): Promise<Response> };
};
export const authEnv = (ctx: Ctx) => ctx.env as unknown as AuthEnv;

export const SESSION_SECONDS = 365 * 24 * 60 * 60;
export const LINK_SECONDS = 15 * 60;
export const IP_LIMIT = 5;
export const IP_WINDOW_SECONDS = 60;
export const ADDRESS_LIMIT = 3;
export const ADDRESS_WINDOW_SECONDS = 15 * 60;
const MIN_KEY = 32;
const PERSON = /^[a-z0-9_]{1,32}$/;
const EMAIL = /^[^\s@,&?=<>"'#%+]+@[^\s@,&?=<>"'#%+]+\.[^\s@,&?=<>"'#%+]+$/;
export const TOKEN = /^[A-Za-z0-9_-]{43}$/;

const enc = new TextEncoder();

/**
 * The address people use when the App sits behind the front door (docs/cutover-v3.md): the origin of SITE_URL,
 * a dashboard variable, https only. Null when unset or odd, so previews and local runs use the request's own origin.
 */
export function publicOrigin(env: AuthEnv): string | null {
  try {
    const url = new URL(env.SITE_URL ?? "");
    return url.protocol === "https:" && !url.username ? url.origin : null;
  } catch {
    return null;
  }
}

/** Local development (Node, tests) sets SP_ENV=dev: guards let everyone in as the owner. The Worker never does. */
export const devMode = (env: AuthEnv) => env.SP_ENV === "dev";

export type Audience = "production" | "preview";
export const audienceOf = (env: AuthEnv): Audience =>
  env.SP_ENV === "preview" ? "preview" : "production";

/** The key that signs this deploy's sessions, or null when it is missing, short, or a preview reusing production's. */
export function cookieKey(env: AuthEnv): string | null {
  const key = audienceOf(env) === "preview" ? env.SP_PREVIEW_COOKIE_KEY : env.SP_COOKIE_KEY;
  if (typeof key !== "string" || key.length < MIN_KEY) return null;
  if (audienceOf(env) === "preview" && key === env.SP_COOKIE_KEY) return null;
  return key;
}
/** Host-only (`__Host-` needs Secure, Path=/ and no Domain); previews use another name too. */
export const cookieName = (env: AuthEnv) =>
  audienceOf(env) === "preview" ? "__Host-sp_preview" : "__Host-sp";

const b64url = (bytes: ArrayBuffer | Uint8Array) => {
  let s = "";
  for (const b of new Uint8Array(bytes)) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
};
function unb64url(text: string): Uint8Array | null {
  if (!/^[A-Za-z0-9_-]+$/.test(text)) return null;
  try {
    return Uint8Array.from(atob(text.replace(/-/g, "+").replace(/_/g, "/")), (c) =>
      c.charCodeAt(0),
    );
  } catch {
    return null;
  }
}

const hmacKey = (secret: string) =>
  crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, [
    "sign",
    "verify",
  ]);

export async function sha256hex(text: string) {
  return [...new Uint8Array(await crypto.subtle.digest("SHA-256", enc.encode(text)))]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}
/** Constant-time equality for two strings of any length: compare their SHA-256 digests. */
export async function sameSecret(given: string, expected: string) {
  if (!given || !expected) return false;
  const [a, b] = await Promise.all([sha256hex(given), sha256hex(expected)]);
  return a === b;
}

export const newToken = () => b64url(crypto.getRandomValues(new Uint8Array(32)));

// ---- people ------------------------------------------------------------------------------------------------------

/** The two addresses, keyed by person id. Bad entries are dropped, never trusted. */
export function people(env: AuthEnv): Record<string, string> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(env.SP_PEOPLE ?? "");
  } catch {
    return {};
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
  const out: Record<string, string> = {};
  for (const [id, email] of Object.entries(parsed)) {
    if (
      id !== "__proto__" &&
      PERSON.test(id) &&
      typeof email === "string" &&
      EMAIL.test(email.trim())
    )
      out[id] = email.trim();
  }
  return out;
}
export const knownPerson = (env: AuthEnv, id: string) => Object.hasOwn(people(env), id);

/** Every entry gets the same constant-time compare, none skipped, so timing does not say which matched. */
export async function personForEmail(env: AuthEnv, email: string): Promise<string | null> {
  let found: string | null = null;
  for (const [id, address] of Object.entries(people(env)))
    if (await sameSecret(email, address.toLowerCase())) found = id;
  return found;
}

// ---- sessions ----------------------------------------------------------------------------------------------------

// Session value: v1.<audience>.<person>.<expires, unix seconds>.<HMAC-SHA256 of the first four parts>
export async function signSession(env: AuthEnv, person: string, nowMs: number): Promise<string> {
  const key = cookieKey(env);
  if (!key) throw new Error("the cookie key is missing or too short");
  if (!PERSON.test(person)) throw new Error("bad person id");
  const body = `v1.${audienceOf(env)}.${person}.${Math.floor(nowMs / 1000) + SESSION_SECONDS}`;
  return `${body}.${b64url(await crypto.subtle.sign("HMAC", await hmacKey(key), enc.encode(body)))}`;
}

export async function verifySession(
  env: AuthEnv,
  value: string,
  nowMs: number,
): Promise<string | null> {
  const key = cookieKey(env);
  if (!key) return null;
  const parts = value.split(".");
  if (parts.length !== 5 || parts[0] !== "v1" || parts[1] !== audienceOf(env)) return null;
  const person = parts[2] as string;
  if (!PERSON.test(person) || !/^\d{1,12}$/.test(parts[3] as string)) return null;
  const sig = unb64url(parts[4] as string);
  if (!sig || sig.length !== 32) return null;
  const ok = await crypto.subtle.verify(
    "HMAC",
    await hmacKey(key),
    sig as BufferSource,
    enc.encode(parts.slice(0, 4).join(".")),
  );
  if (!ok) return null;
  const expires = Number(parts[3]);
  const now = Math.floor(nowMs / 1000);
  if (expires <= now || expires > now + SESSION_SECONDS + 60) return null;
  return person;
}

export function readCookie(request: Request, name: string): string | null {
  for (const part of (request.headers.get("Cookie") ?? "").split(";")) {
    const i = part.indexOf("=");
    if (i > 0 && part.slice(0, i).trim() === name) return part.slice(i + 1).trim();
  }
  return null;
}

/** Who this request is, or null. A person no longer in SP_PEOPLE is signed out. */
export async function sessionPerson(ctx: Ctx, request: Request): Promise<string | null> {
  const env = authEnv(ctx);
  const value = readCookie(request, cookieName(env));
  if (!value) return null;
  const person = await verifySession(env, value, ctx.now().getTime());
  return person && knownPerson(env, person) ? person : null;
}

const attrs = "Path=/; HttpOnly; Secure; SameSite=Lax";
export const sessionCookie = (env: AuthEnv, value: string) =>
  `${cookieName(env)}=${value}; Max-Age=${SESSION_SECONDS}; ${attrs}`;
export const clearedCookie = (env: AuthEnv) => `${cookieName(env)}=; Max-Age=0; ${attrs}`;

/** Where to go after sign-in: only a path on this site, never back to /login. */
export function safeNext(next: unknown): string {
  if (typeof next !== "string" || next.length > 2048 || !next.startsWith("/")) return "/";
  // biome-ignore lint/suspicious/noControlCharactersInRegex: rejecting control characters is the point
  if (next.startsWith("//") || next.includes("\\") || /[\u0000-\u001f\u007f]/.test(next))
    return "/";
  const path = (next.split(/[?#]/)[0] as string).toLowerCase();
  return path === "/login" || path.startsWith("/login/") ? "/" : next;
}

// ---- guards for other areas --------------------------------------------------------------------------------------

type Next = () => Promise<void>;
/** Owner-only writes (feedback review, money settings): the father gets 403, a stranger 401. */
export const ownerOnly =
  (ctx: Ctx) =>
  async (c: Context, next: Next): Promise<Response | undefined> => {
    if (devMode(authEnv(ctx))) return void (await next());
    const person = await sessionPerson(ctx, c.req.raw);
    if (!person) return c.json({ error: "login_needed" }, 401);
    if (person !== "owner") return c.json({ error: "owner_only" }, 403);
    c.set("person", person);
    await next();
  };
