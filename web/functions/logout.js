// POST /logout clears the session cookie. Behind the middleware, so it needs a session.
import { clearedCookie } from "../lib/auth.js";
import { SECURITY_HEADERS } from "../lib/login-page.js";

export async function onRequestPost() {
  return new Response(null, { status: 303, headers: { Location: "/login", "Set-Cookie": clearedCookie(), ...SECURITY_HEADERS } });
}
