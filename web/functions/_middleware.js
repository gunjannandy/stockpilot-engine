// Guards every route on the site (ADR 0005). Closed by default:
//   /api/vm/*   only with header X-SP-Key equal to SP_VM_KEY (the VM; a browser session is not enough)
//   /api/v2/ingest   only with header X-SP-Ingest-Key equal to SP_INGEST_KEY (public jobs; write-only)
//   /login, /login/verify   open (the sign-in buttons, and the emailed link's Sign in button)
//   anything    else only with a valid session cookie; context.data.person names who it is
// Browser POST/PUT/PATCH/DELETE must come from this site (Origin check), because the cookie is
// SameSite=Lax so that the Kite redirect back to /kite/callback still carries it.
import { sessionPerson, sameSecret, vmKeyUsable, ingestAllowed } from "../lib/auth.js";

const SAFE = new Set(["GET", "HEAD", "OPTIONS"]);

const json = (status, body) => new Response(JSON.stringify(body), {
  status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
});

// A real Origin must match this site. Some browsers send no Origin, or "null", on a form POST from a
// page with a strict referrer policy; then the browser-set Sec-Fetch-Site (no page script can forge it)
// must say same-origin.
function sameOrigin(request, url) {
  const origin = request.headers.get("Origin");
  if (origin !== null && origin !== "null") return origin === url.origin;
  return request.headers.get("Sec-Fetch-Site") === "same-origin";
}

export async function onRequest(context) {
  const { request, env } = context;
  const url = new URL(request.url);
  const path = url.pathname;

  if (path === "/api/vm" || path.startsWith("/api/vm/")) {
    const key = env?.SP_VM_KEY;
    if (vmKeyUsable(key) && (await sameSecret(request.headers.get("X-SP-Key"), key))) return context.next();
    return json(401, { error: "bad_vm_key" });
  }

  // Public jobs write news and quotes here with their own write-only key (no cookie, no Origin).
  if (path === "/api/v2/ingest") {
    return (await ingestAllowed(request, env)) ? context.next() : json(401, { error: "bad_ingest_key" });
  }

  if (!SAFE.has(request.method) && !sameOrigin(request, url)) return json(403, { error: "cross_site" });

  if (path === "/login" || path === "/login/verify") return context.next();

  const person = await sessionPerson(request, env);
  if (person) {
    context.data.person = person;
    return context.next();
  }
  if (path.startsWith("/api/")) return json(401, { error: "login_needed" });
  const next = path + url.search;
  return new Response(null, {
    status: 302,
    headers: { Location: next === "/" ? "/login" : `/login?next=${encodeURIComponent(next)}`, "Cache-Control": "no-store" },
  });
}
