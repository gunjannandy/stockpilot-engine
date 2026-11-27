// GET /login shows one email box and names nobody; POST /login emails a single-use link to a known address (ADR 0006).
// Open without a session (the middleware lets /login through after its same-origin check).
import {
  people, personForEmail, newToken, linkKey, sessionPerson, safeNext, cookieKeyUsable, sha256hex,
  waitFor, record, LINK_SECONDS, PERSON_LIMIT, PERSON_WINDOW_SECONDS, IP_LIMIT, IP_WINDOW_SECONDS,
} from "../lib/auth.js";
import { loginPage, sentPage, htmlResponse, SECURITY_HEADERS } from "../lib/login-page.js";

const BRIDGE_TIMEOUT_MS = 25_000;

const redirect = (to) => new Response(null, { status: 303, headers: { Location: to, ...SECURITY_HEADERS } });
const MAX_EMAIL = 254;

export async function onRequestGet({ request, env }) {
  const next = safeNext(new URL(request.url).searchParams.get("next"));
  if (await sessionPerson(request, env)) return redirect(next);
  return htmlResponse(loginPage({ next }));
}

// Asks the Google bridge to send the email. True only on {ok: true}.
async function sendLink(env, to, token) {
  try {
    const url = new URL(env.GOOGLE_BRIDGE_URL);
    url.search = new URLSearchParams({ key: env.GOOGLE_BRIDGE_KEY, op: "signin", to, t: token }).toString();
    const res = await fetch(url.toString(), { redirect: "follow", signal: AbortSignal.timeout(BRIDGE_TIMEOUT_MS) });
    if (!res.ok) return false;
    return (await res.json())?.ok === true;
  } catch { return false; }
}

async function readFields(request) {
  try {
    if ((request.headers.get("Content-Type") || "").includes("json")) {
      const body = await request.json();
      return body && typeof body === "object" ? { email: body.email, next: body.next } : {};
    }
    const f = await request.formData();
    return { email: f.get("email"), next: f.get("next") };
  } catch { return {}; }
}

// Stores the link and sends the email. Runs after the response (waitUntil), so the answer's
// timing does not depend on the address. A failure is logged without the address or token.
async function issueLink(env, person, to, next) {
  const token = newToken();
  const key = await linkKey(token);
  try {
    await env.SP.put(key, JSON.stringify({ person, next }), { expiration: Math.floor(Date.now() / 1000) + LINK_SECONDS });
    if (!(await sendLink(env, to, token))) throw new Error("the bridge did not send the email");
  } catch (err) {
    console.error("sign-in link not sent:", err?.message || "error");
    try { await env.SP.delete(key); } catch { /* the entry expires in 15 minutes anyway */ }
  }
}

export async function onRequestPost(context) {
  const { request, env } = context;
  if (!env?.SP || !cookieKeyUsable(env.SP_COOKIE_KEY) || Object.keys(people(env)).length === 0 || !env.GOOGLE_BRIDGE_URL || !env.GOOGLE_BRIDGE_KEY) {
    return htmlResponse(loginPage({ message: "Sign-in is not set up yet." }), 503);
  }
  const fields = await readFields(request);
  const next = safeNext(fields.next);
  const typed = typeof fields.email === "string" ? fields.email : "";
  const email = typed.trim().toLowerCase();
  const wellFormed = email.length > 0 && email.length <= MAX_EMAIL && email.includes("@");

  // Every address is counted, known or not, with the same KV work, so limits and timing tell nothing.
  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  const addrKey = `rl:addr:${await sha256hex(email.slice(0, MAX_EMAIL + 1))}`, ipKey = `rl:ip:${ip}`;
  const [ipWait, addrWait] = [await waitFor(env.SP, ipKey, IP_LIMIT), await waitFor(env.SP, addrKey, PERSON_LIMIT)];
  if (ipWait > 0) {
    return htmlResponse(loginPage({ next, message: "Too many tries. Wait an hour." }), 429, { "Retry-After": String(ipWait) });
  }
  await record(env.SP, ipKey, IP_WINDOW_SECONDS);
  await record(env.SP, addrKey, PERSON_WINDOW_SECONDS);

  const person = wellFormed ? await personForEmail(env, email) : null;
  const response = htmlResponse(sentPage());
  if (person && addrWait === 0) {
    context.waitUntil(issueLink(env, person, people(env)[person], next));
  }
  return response;
}
