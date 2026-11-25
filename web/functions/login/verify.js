// The emailed link lands here (ADR 0006).
// GET shows a Sign in button and never spends the link, because mail scanners open links.
// POST spends it (read, then delete) and sets the one-year session cookie in this browser.
import { TOKEN, linkKey, knownPerson, safeNext, signSession, sessionCookie, cookieKeyUsable } from "../../lib/auth.js";
import { confirmPage, expiredPage, loginPage, htmlResponse, SECURITY_HEADERS } from "../../lib/login-page.js";

async function readLink(kv, token) {
  if (typeof token !== "string" || !TOKEN.test(token)) return { key: null, link: null };
  const key = await linkKey(token);
  return { key, link: await kv.get(key, "json") };
}

export async function onRequestGet({ request, env }) {
  if (!env?.SP) return htmlResponse(loginPage({ message: "Sign-in is not set up yet." }), 503);
  const token = new URL(request.url).searchParams.get("t");
  const { link } = await readLink(env.SP, token);
  if (!link || !knownPerson(env, link.person)) return htmlResponse(expiredPage());
  return htmlResponse(confirmPage(token));
}

export async function onRequestPost({ request, env }) {
  if (!env?.SP || !cookieKeyUsable(env.SP_COOKIE_KEY)) return htmlResponse(loginPage({ message: "Sign-in is not set up yet." }), 503);
  let token = null;
  try { token = (await request.formData()).get("t"); } catch { /* falls through to the expired page */ }
  const { key, link } = await readLink(env.SP, token);
  if (!link) return htmlResponse(expiredPage(), 400);
  await env.SP.delete(key); // single use, even if the person has since been removed
  if (!knownPerson(env, link.person)) return htmlResponse(expiredPage(), 400);
  const value = await signSession(link.person, env.SP_COOKIE_KEY);
  return new Response(null, { status: 303, headers: { Location: safeNext(link.next), ...SECURITY_HEADERS, "Set-Cookie": sessionCookie(value) } });
}
