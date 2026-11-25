import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { onRequestGet as loginPage, onRequestPost as login } from "../functions/login.js";
import { onRequestGet as verifyPage, onRequestPost as verify } from "../functions/login/verify.js";
import { onRequestPost as logout } from "../functions/logout.js";
import { onRequest as middleware } from "../functions/_middleware.js";
import { verifySession, signSession, SESSION_SECONDS } from "../lib/auth.js";
import { BRIDGE_KEY, BRIDGE_URL, COOKIE_KEY, PEOPLE, makeEnv, fakeBridge, req, run, form, setCookieValue } from "./fakes.mjs";

const post = (fields, opts = {}) => req("/login", { method: "POST", ...form(fields), ...opts });
const postVerify = (t, opts = {}) => req("/login/verify", { method: "POST", ...form({ t }), ...opts });
const linkKeys = (env) => [...env.SP.map.keys()].filter((k) => k.startsWith("link:"));
const sha = (t) => createHash("sha256").update(t).digest("hex");

const SAME_WORDS = /If that address can sign in, we have emailed a link\. Open it on this computer; it works once, for 15 minutes\./;
const asked = async (email, env, opts = {}) => {
  const out = await run(login, post({ email, next: opts.next ?? "/" }, opts), env);
  await out.settle();
  return out;
};

// Asks for a link and returns the token the fake bridge was given.
async function ask(t, env, person = "father", next = "/") {
  const calls = fakeBridge(t);
  const { response } = await asked(PEOPLE[person], env, { next });
  assert.equal(response.status, 200);
  return { token: calls[0].params.t, calls, response };
}

test("GET /login is one email box and a button, names nobody, and keeps next", async () => {
  const { response } = await run(loginPage, req("/login?next=/kite/callback%3Frequest_token%3Dabc"), makeEnv());
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /<form method="post" action="\/login"/);
  assert.match(html, /<input[^>]*type="email"[^>]*name="email"|<input[^>]*name="email"[^>]*type="email"/);
  assert.match(html, />\s*Send sign-in link\s*</);
  assert.match(html, /value="\/kite\/callback\?request_token=abc"/);
  assert.doesNotMatch(html, /father|owner|name="person"|I(&#39;|')m /i);
  assert.doesNotMatch(html, /pass(word|phrase)|<script|https?:\/\/|example\.test/i);
  assert.match(response.headers.get("Content-Security-Policy"), /default-src 'none'/);
  assert.equal(response.headers.get("X-Frame-Options"), "DENY");
});

test("the next field is escaped and cannot point off-site", async () => {
  const { response } = await run(loginPage, req("/login?next=" + encodeURIComponent('/x"><script>alert(1)</script>')), makeEnv());
  assert.doesNotMatch(await response.text(), /<script>/);
  for (const bad of ["//evil.example", "https://evil.example", "/\\evil.example"]) {
    const evil = await run(loginPage, req("/login?next=" + encodeURIComponent(bad)), makeEnv());
    assert.match(await evil.response.text(), /name="next" value="\/"/, bad);
  }
});

test("a known address reaches the bridge with its own address, after the response, and the page leaks nothing", async (t) => {
  for (const [person, email] of Object.entries(PEOPLE)) {
    t.mock.restoreAll();
    const env = makeEnv();
    const calls = fakeBridge(t);
    const out = await run(login, post({ email }), env);
    assert.equal(calls.length, 0, "nothing sent before waitUntil runs");
    await out.settle();
    assert.equal(calls.length, 1);
    const token = calls[0].params.t;
    assert.equal(calls[0].base, BRIDGE_URL);
    assert.equal(calls[0].params.key, BRIDGE_KEY);
    assert.equal(calls[0].params.op, "signin");
    assert.equal(calls[0].params.to, email);
    assert.match(token, /^[A-Za-z0-9_-]{43}$/);
    assert.equal(out.response.status, 200);
    const html = await out.response.text();
    assert.match(html, SAME_WORDS);
    for (const secret of [token, email, BRIDGE_KEY, "example.test", "Father", "Owner"]) assert.ok(!html.includes(secret), `page leaks ${secret}`);
    assert.equal(out.response.headers.get("Set-Cookie"), null);
    assert.deepEqual(linkKeys(env), ["link:" + sha(token)], "only the token's hash is stored");
    assert.deepEqual(JSON.parse(env.SP.map.get("link:" + sha(token)).value), { person, next: "/" });
  }
});

test("known and unknown addresses get byte-identical answers; only the known one reaches the bridge", async (t) => {
  const calls = fakeBridge(t);
  const answers = [];
  for (const email of [PEOPLE.father, "stranger@example.test", "", "no-at-sign", "a".repeat(250) + "@x.test", "x@y@z", "__proto__"]) {
    const out = await asked(email, makeEnv());
    answers.push({ email, status: out.response.status, body: await out.response.text(), headers: [...out.response.headers].sort().join("|") });
  }
  for (const a of answers) {
    assert.equal(a.status, 200, a.email);
    assert.equal(a.body, answers[0].body, a.email);
    assert.equal(a.headers, answers[0].headers, a.email);
  }
  assert.match(answers[0].body, SAME_WORDS);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].params.to, PEOPLE.father);
});

test("upper case and spaces still match, and the bridge gets the stored address", async (t) => {
  const calls = fakeBridge(t);
  await asked("  Owner@Example.TEST  ", makeEnv());
  assert.equal(calls.length, 1);
  assert.equal(calls[0].params.to, PEOPLE.owner);
  const env = makeEnv({ SP_PEOPLE: JSON.stringify({ father: "Father@Example.test" }) });
  await asked("father@example.test", env);
  assert.equal(calls.length, 2, "a mixed-case stored address matches too");
});

test("the same answer comes whether or not the bridge works, and its failure is logged without address or token", async (t) => {
  const logged = [];
  for (const reply of [() => ({ error: "recipient not allowed" }), () => new Response("boom", { status: 500 }), () => { throw new Error("network down"); },
    () => new Response("<html>not json</html>", { status: 200 }), () => ({ ok: false })]) {
    t.mock.restoreAll();
    t.mock.method(console, "error", (...a) => logged.push(a.map(String).join(" ")));
    const calls = fakeBridge(t, reply);
    const env = makeEnv();
    const bad = await asked(PEOPLE.father, env, { next: "/holdings" });
    const good = await asked("nobody@example.test", makeEnv());
    assert.equal(bad.response.status, 200);
    assert.equal(await bad.response.text(), await good.response.text());
    assert.equal(calls.length, 1);
    assert.deepEqual(linkKeys(env), [], "no KV entry left");
  }
  assert.equal(logged.length, 5, "each failure is logged");
  for (const line of logged) for (const secret of [PEOPLE.father, "example.test", BRIDGE_KEY, "father"]) assert.ok(!line.toLowerCase().includes(secret.toLowerCase()), `log leaks ${secret}: ${line}`);
});

test("3 per address per 15 minutes: the fourth is the same 200 page and sends nothing; other people and later times are fine", async (t) => {
  let now = Date.parse("2026-11-22T10:00:00Z");
  t.mock.method(Date, "now", () => now);
  const calls = fakeBridge(t);
  const env = makeEnv();
  const bodies = [];
  for (let i = 0; i < 4; i++) {
    const out = await asked(PEOPLE.father, env, { ip: `198.51.100.${i}` });
    assert.equal(out.response.status, 200, `try ${i + 1}`);
    bodies.push(await out.response.text());
  }
  assert.equal(calls.length, 3, "the fourth sent nothing");
  assert.ok(bodies.every((b) => b === bodies[0]), "the fourth looks the same");
  assert.equal(linkKeys(env).length, 3);
  await asked(PEOPLE.owner, env);
  assert.equal(calls.length, 4, "the other person is not limited");
  now += 15 * 60 * 1000 + 1000;
  await asked(PEOPLE.father, env);
  assert.equal(calls.length, 5, "lifts after 15 minutes");
});

test("the person limit counts unknown addresses too, so it cannot tell them apart", async (t) => {
  fakeBridge(t);
  const env = makeEnv();
  for (let i = 0; i < 5; i++) await asked("stranger@example.test", env, { ip: `198.51.100.${i}` });
  const keys = [...env.SP.map.keys()];
  assert.ok(keys.some((k) => k.startsWith("rl:") && !k.startsWith("rl:ip:")), "an unknown address is counted");
  assert.ok(!keys.join(" ").includes("stranger"), "the address itself is not stored as a key");
});

test("10 per IP per hour, counted for any address, then 429 'Wait an hour'", async (t) => {
  let now = Date.parse("2026-11-22T10:00:00Z");
  t.mock.method(Date, "now", () => now);
  const calls = fakeBridge(t);
  const env = makeEnv();
  for (let i = 0; i < 10; i++) {
    const email = i % 3 === 0 ? PEOPLE.father : i % 3 === 1 ? PEOPLE.owner : `nobody${i}@example.test`;
    const out = await asked(email, env);
    assert.equal(out.response.status, 200, `try ${i + 1}`);
    if (i < 9) now += 6 * 60 * 1000;
  }
  const over = await asked(PEOPLE.father, env);
  assert.equal(over.response.status, 429);
  assert.match(await over.response.text(), /Too many tries\. Wait an hour\./);
  assert.ok(Number(over.response.headers.get("Retry-After")) > 0);
  const sent = calls.length;
  assert.equal((await asked("junk", env)).response.status, 429, "malformed counts too");
  assert.equal(calls.length, sent);
  assert.equal((await asked(PEOPLE.father, env, { ip: "198.51.100.9" })).response.status, 200, "another IP is fine");
  now += 60 * 60 * 1000;
  assert.equal((await asked(PEOPLE.father, env)).response.status, 200, "lifts after an hour");
});

test("JSON bodies work too, and a missing or non-text email gets the same page", async (t) => {
  const calls = fakeBridge(t);
  const out = await run(login, req("/login", { method: "POST", body: JSON.stringify({ email: PEOPLE.father, next: "/holdings" }), headers: { "Content-Type": "application/json" } }), makeEnv());
  await out.settle();
  assert.equal(calls.length, 1);
  for (const body of ["{}", "[]", "null", "not json", JSON.stringify({ email: 5 }), JSON.stringify({ email: [PEOPLE.father] })]) {
    const o = await run(login, req("/login", { method: "POST", body, headers: { "Content-Type": "application/json" } }), makeEnv());
    await o.settle();
    assert.equal(o.response.status, 200, body);
    assert.match(await o.response.text(), SAME_WORDS);
  }
  assert.equal(calls.length, 1);
});

test("login refuses to work when secrets, KV or the bridge settings are missing", async (t) => {
  const calls = fakeBridge(t);
  for (const missing of [{ SP_COOKIE_KEY: undefined }, { SP: undefined }, { SP_PEOPLE: undefined }, { SP_PEOPLE: "not json" },
    { GOOGLE_BRIDGE_URL: undefined }, { GOOGLE_BRIDGE_KEY: undefined }]) {
    const { response } = await run(login, post({ email: PEOPLE.father }), makeEnv(missing));
    assert.ok(response.status >= 500, JSON.stringify(Object.keys(missing)) + " → " + response.status);
    assert.equal(response.headers.get("Set-Cookie"), null);
  }
  assert.equal(calls.length, 0);
});

test("GET /login/verify with a good token shows a Sign in button and does not spend the link", async (t) => {
  const env = makeEnv();
  const { token } = await ask(t, env);
  for (let i = 0; i < 3; i++) {
    const { response } = await run(verifyPage, req("/login/verify?t=" + token), env);
    assert.equal(response.status, 200);
    assert.equal(response.headers.get("Set-Cookie"), null);
    const html = await response.text();
    assert.match(html, /<form method="post" action="\/login\/verify"/);
    assert.match(html, />\s*Sign in\s*</);
    assert.match(html, new RegExp(`name="t" value="${token}"`));
    assert.doesNotMatch(html, /<script/);
    assert.match(response.headers.get("Referrer-Policy"), /no-referrer|same-origin/);
  }
  assert.equal(linkKeys(env).length, 1, "still there");
  assert.equal((await run(verify, postVerify(token), env)).response.status, 303, "and still usable");
});

test("GET /login/verify with a junk, missing or used token shows the expired page", async () => {
  const env = makeEnv();
  for (const q of ["", "?t=", "?t=junk", "?t=" + "A".repeat(43), "?t=" + "A".repeat(44), "?t=<script>"]) {
    const { response } = await run(verifyPage, req("/login/verify" + q), env);
    assert.equal(response.status, 200, q);
    const html = await response.text();
    assert.match(html, /This link has expired or was used\. Ask for a new one\./);
    assert.match(html, /href="\/login"/);
    assert.doesNotMatch(html, /<form/);
  }
});

test("POST /login/verify signs in the right person, once, and goes to next", async (t) => {
  for (const person of Object.keys(PEOPLE)) {
    t.mock.restoreAll();
    const env = makeEnv();
    const { token } = await ask(t, env, person, "/kite/callback?request_token=abc");
    const { response } = await run(verify, postVerify(token), env);
    assert.equal(response.status, 303);
    assert.equal(response.headers.get("Location"), "/kite/callback?request_token=abc");
    const raw = response.headers.get("Set-Cookie");
    for (const attr of ["HttpOnly", "Secure", "SameSite=Lax", "Path=/", `Max-Age=${SESSION_SECONDS}`]) assert.ok(raw.includes(attr), `cookie has ${attr}: ${raw}`);
    assert.equal(await verifySession(setCookieValue(response), COOKIE_KEY, Date.now()), person);
    assert.deepEqual(linkKeys(env), [], "spent");
  }
});

test("the same token cannot be used twice", async (t) => {
  const env = makeEnv();
  const { token } = await ask(t, env);
  assert.equal((await run(verify, postVerify(token), env)).response.status, 303);
  const again = await run(verify, postVerify(token), env);
  assert.equal(again.response.status, 400);
  assert.equal(again.response.headers.get("Set-Cookie"), null);
  assert.match(await again.response.text(), /expired or was used/);
});

test("an expired token fails, and so do forged ones", async (t) => {
  let now = Date.parse("2026-11-22T10:00:00Z");
  t.mock.method(Date, "now", () => now);
  const env = makeEnv();
  const { token } = await ask(t, env);
  const flipped = (token[0] === "A" ? "B" : "A") + token.slice(1);
  for (const bad of [flipped, "A".repeat(43), "", "junk", token + "x", token.slice(1)]) {
    const { response } = await run(verify, postVerify(bad), env);
    assert.equal(response.status, 400, bad);
    assert.equal(response.headers.get("Set-Cookie"), null);
  }
  assert.equal(linkKeys(env).length, 1, "forged tries do not spend the real link");
  now += 15 * 60 * 1000 + 1000;
  const late = await run(verify, postVerify(token), env);
  assert.equal(late.response.status, 400);
  assert.equal(late.response.headers.get("Set-Cookie"), null);
  const lateGet = await run(verifyPage, req("/login/verify?t=" + token), env);
  assert.match(await lateGet.response.text(), /expired or was used/);
});

test("a token whose person was removed from SP_PEOPLE does not sign in", async (t) => {
  const env = makeEnv();
  const { token } = await ask(t, env, "father");
  env.SP_PEOPLE = JSON.stringify({ owner: PEOPLE.owner });
  const { response } = await run(verify, postVerify(token), env);
  assert.equal(response.status, 400);
  assert.equal(response.headers.get("Set-Cookie"), null);
});

test("next cannot send the person off-site after sign-in", async (t) => {
  for (const bad of ["//evil.example", "https://evil.example", "/\\evil.example", "/login/verify?t=x"]) {
    t.mock.restoreAll();
    const env = makeEnv();
    const { token } = await ask(t, env, "father", bad);
    const { response } = await run(verify, postVerify(token), env);
    assert.equal(response.status, 303);
    assert.equal(response.headers.get("Location"), "/", bad);
  }
});

test("verify refuses when the cookie key is missing, without spending the link", async (t) => {
  const env = makeEnv();
  const { token } = await ask(t, env);
  const { response } = await run(verify, postVerify(token), { ...env, SP_COOKIE_KEY: undefined });
  assert.ok(response.status >= 500);
  assert.equal(response.headers.get("Set-Cookie"), null);
  assert.equal(linkKeys(env).length, 1);
});

test("GET /login with a valid session goes straight on", async () => {
  const env = makeEnv();
  const value = await signSession("father", COOKIE_KEY, Date.now());
  const { response } = await run(loginPage, req("/login?next=/holdings", { headers: { Cookie: `sp_session=${value}` } }), env);
  assert.equal(response.status, 303);
  assert.equal(response.headers.get("Location"), "/holdings");
});

test("logout clears the cookie", async () => {
  const { response } = await run(logout, req("/logout", { method: "POST" }), makeEnv(), { person: "father" });
  assert.equal(response.status, 303);
  assert.match(response.headers.get("Set-Cookie"), /sp_session=;.*Max-Age=0/);
});

test("full flow: ask, press the link, then the cookie opens the API through the middleware", async (t) => {
  const env = makeEnv();
  // The login page and the verify page are open without a session.
  assert.equal((await run(middleware, post({ email: PEOPLE.father }), env)).passed, true);
  assert.equal((await run(middleware, req("/login/verify?t=x"), env)).passed, true);
  assert.equal((await run(middleware, postVerify("x"), env)).passed, true);
  const { token } = await ask(t, env);
  const { response } = await run(verify, postVerify(token), env);
  const cookie = `sp_session=${setCookieValue(response)}`;
  const { passed, data } = await run(middleware, req("/api/queue", { method: "POST", headers: { Cookie: cookie } }), env);
  assert.equal(passed, true);
  assert.equal(data.person, "father");
});

test("a cross-site POST to /login/verify is refused by the middleware", async () => {
  const { passed, response } = await run(middleware, postVerify("x", { origin: "https://evil.example" }), makeEnv());
  assert.equal(passed, false);
  assert.equal(response.status, 403);
});
