import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { onRequest as middleware } from "../functions/_middleware.js";
import { onRequestGet as me } from "../functions/api/me.js";
import { signSession } from "../lib/auth.js";
import { COOKIE_KEY, VM_KEY, ORIGIN, makeEnv, req, run } from "./fakes.mjs";

const cookie = async (person = "father", key = COOKIE_KEY) => ({ Cookie: `theme=dark; sp_session=${await signSession(person, key, Date.now())}` });

// Every route file under web/functions, as a URL path ([id] → a sample value). Lane A's routes
// land here after the merge, so this test keeps covering them.
function routes() {
  const root = fileURLToPath(new URL("../functions/", import.meta.url));
  const out = [];
  const walk = (dir) => {
    for (const name of readdirSync(dir)) {
      const full = join(dir, name);
      if (statSync(full).isDirectory()) { walk(full); continue; }
      if (!/\.(js|ts|mjs)$/.test(name) || name.startsWith("_middleware")) continue;
      let path = "/" + relative(root, full).replace(/\\/g, "/").replace(/\.(js|ts|mjs)$/, "");
      path = path.replace(/\/index$/, "/").replace(/\[\[?[^\]]+\]\]?/g, "123");
      out.push(path);
    }
  };
  walk(root);
  return out;
}

test("every route except /login and /login/verify is closed without a session", async () => {
  const paths = [...routes(), "/", "/index.html", "/today.json", "/tabs/holdings.json", "/LOGIN", "/login/x", "/login/verify/", "/login/verifyx", "/login.html",
    "/api/me", "/api/queue", "/api/queue/1", "/kite/login", "/kite/callback?request_token=abc", "/logout"];
  assert.ok(paths.includes("/api/me") && paths.includes("/login") && paths.includes("/login/verify"), "route walk found the login routes");
  for (const path of paths) {
    for (const method of ["GET", "POST", "DELETE"]) {
      const { response, passed } = await run(middleware, req(path, { method }), makeEnv());
      if (path === "/login" || path === "/login/verify") { assert.equal(passed, true, `${method} ${path} must be open`); continue; }
      assert.equal(passed, false, `${method} ${path} let through without a session`);
      assert.ok([302, 401].includes(response.status), `${method} ${path} → ${response.status}`);
    }
  }
});

test("a page without a session redirects to /login and keeps where it was going", async () => {
  const { response } = await run(middleware, req("/kite/callback?request_token=abc&status=success"), makeEnv());
  assert.equal(response.status, 302);
  const loc = new URL(response.headers.get("Location"), ORIGIN);
  assert.equal(loc.pathname, "/login");
  assert.equal(loc.searchParams.get("next"), "/kite/callback?request_token=abc&status=success");
});

test("an API call without a session gets JSON 401, not a redirect", async () => {
  const { response } = await run(middleware, req("/api/queue", { method: "POST" }), makeEnv());
  assert.equal(response.status, 401);
  assert.deepEqual(await response.json(), { error: "login_needed" });
});

test("a valid session lets the request through and names the person", async () => {
  const { passed, data } = await run(middleware, req("/api/queue", { method: "POST", headers: await cookie("owner") }), makeEnv());
  assert.equal(passed, true);
  assert.equal(data.person, "owner");
});

test("GET /api/me returns the person from the session", async () => {
  const env = makeEnv(), data = {};
  const first = await run(middleware, req("/api/me", { headers: await cookie("father") }), env, data);
  assert.equal(first.passed, true);
  const { response } = await run(me, req("/api/me"), env, data);
  assert.deepEqual(await response.json(), { person: "father" });
  assert.match(response.headers.get("Cache-Control"), /no-store/);
});

test("forged, expired, tampered and wrong-key cookies are refused", async (t) => {
  const env = makeEnv();
  const good = await signSession("father", COOKIE_KEY, Date.now());
  const [v, person, exp, sig] = good.split(".");
  const bad = {
    tampered: [v, person, exp, sig.slice(0, -2) + (sig.endsWith("AA") ? "BB" : "AA")].join("."),
    forged: await signSession("father", "an-attacker-guessed-key-of-good-length!!", Date.now()),
    "replayed as the other person": [v, "owner", exp, sig].join("."),
    "person removed from SP_PEOPLE": await signSession("ghost", COOKIE_KEY, Date.now()),
  };
  for (const [name, value] of Object.entries(bad)) {
    const { passed, response } = await run(middleware, req("/api/me", { headers: { Cookie: `sp_session=${value}` } }), env);
    assert.equal(passed, false, name);
    assert.equal(response.status, 401, name);
  }
  // Expired: sign now, check a year and a day later.
  const later = Date.now() + 366 * 24 * 3600 * 1000;   // relative: a fixed date stops being "a year later" as the calendar moves
  t.mock.method(Date, "now", () => later);
  const { passed } = await run(middleware, req("/api/me", { headers: { Cookie: `sp_session=${good}` } }), env);
  assert.equal(passed, false, "expired");
});

test("rotating SP_COOKIE_KEY signs everybody out", async () => {
  const headers = await cookie("father");
  const { passed } = await run(middleware, req("/api/me", { headers }), makeEnv({ SP_COOKIE_KEY: "a-brand-new-cookie-key-after-rotation!!" }));
  assert.equal(passed, false);
});

test("/api/vm/* needs X-SP-Key; a session cookie is not enough", async () => {
  const env = makeEnv();
  const cases = [
    ["missing key", {}, false],
    ["wrong key", { "X-SP-Key": VM_KEY + "x" }, false],
    ["empty key", { "X-SP-Key": "" }, false],
    ["cookie only", await cookie("father"), false],
    ["right key", { "X-SP-Key": VM_KEY }, true],
  ];
  for (const path of ["/api/vm/kite", "/api/vm/queue?after=3", "/api/vm/queue/ack"]) {
    for (const [name, headers, ok] of cases) {
      const method = path.endsWith("ack") ? "POST" : "GET";
      const { passed, response } = await run(middleware, req(path, { method, headers, origin: null }), env);
      assert.equal(passed, ok, `${name} ${path}`);
      if (!ok) assert.equal(response.status, 401, `${name} ${path}`);
    }
  }
});

test("an unset or short SP_VM_KEY closes /api/vm/* instead of opening it", async () => {
  for (const key of [undefined, "", "short"]) {
    const { passed } = await run(middleware, req("/api/vm/kite", { headers: { "X-SP-Key": key ?? "" } }), makeEnv({ SP_VM_KEY: key }));
    assert.equal(passed, false, String(key));
  }
});

test("X-SP-Key does not open browser routes", async () => {
  const { passed } = await run(middleware, req("/api/me", { headers: { "X-SP-Key": VM_KEY } }), makeEnv());
  assert.equal(passed, false);
});

test("a cross-site POST or DELETE is refused even with a session", async () => {
  const headers = await cookie("father");
  for (const origin of ["https://evil.example", null, "null"]) {
    for (const method of ["POST", "DELETE"]) {
      const { passed, response } = await run(middleware, req("/api/queue/1", { method, headers, origin }), makeEnv());
      assert.equal(passed, false, `${method} from ${origin}`);
      assert.equal(response.status, 403);
    }
  }
  const login = await run(middleware, req("/login", { method: "POST", origin: "https://evil.example" }), makeEnv());
  assert.equal(login.passed, false, "login CSRF");
});

test("a missing cookie key closes everything except /login", async () => {
  const env = makeEnv({ SP_COOKIE_KEY: undefined });
  const { passed } = await run(middleware, req("/api/me", { headers: await cookie("father") }), env);
  assert.equal(passed, false);
});

// Brave and Chrome send `Origin: null` on a form POST from a page served with Referrer-Policy
// no-referrer; the owner hit this pressing "Sign in" on /login/verify (2026-11-22).
test("a same-origin form POST with Origin null passes on the browser's Sec-Fetch-Site", async () => {
  for (const origin of [null, "null"]) {
    const ok = await run(middleware, req("/login/verify", { method: "POST", origin, headers: { "Sec-Fetch-Site": "same-origin" } }), makeEnv());
    assert.equal(ok.passed, true, `Origin ${origin} + same-origin`);
    for (const site of ["cross-site", "same-site", "none"]) {
      const bad = await run(middleware, req("/login/verify", { method: "POST", origin, headers: { "Sec-Fetch-Site": site } }), makeEnv());
      assert.equal(bad.passed, false, `Origin ${origin} + ${site}`);
      assert.equal(bad.response.status, 403);
    }
  }
  const evil = await run(middleware, req("/login/verify", { method: "POST", origin: "https://evil.example", headers: { "Sec-Fetch-Site": "same-origin" } }), makeEnv());
  assert.equal(evil.passed, false, "a real foreign Origin wins over Sec-Fetch-Site");
});

test("sign-in pages keep the referrer on this site so the browser sends a real Origin", async () => {
  const { SECURITY_HEADERS } = await import("../lib/login-page.js");
  assert.equal(SECURITY_HEADERS["Referrer-Policy"], "same-origin");
});
