import { test } from "node:test";
import assert from "node:assert/strict";
import {
  people, displayName, signSession, verifySession, sameSecret, safeNext, SESSION_SECONDS,
} from "../lib/auth.js";
import { COOKIE_KEY, makeEnv, PEOPLE } from "./fakes.mjs";

test("people come from SP_PEOPLE and nowhere else", () => {
  assert.deepEqual(people(makeEnv()), PEOPLE);
  assert.deepEqual(people(makeEnv({ SP_PEOPLE: JSON.stringify({ owner: "g@example.test" }) })), { owner: "g@example.test" });
  for (const bad of [undefined, "", "not json", "[]", "null", '"x"', "{}"]) assert.deepEqual(people(makeEnv({ SP_PEOPLE: bad })), {}, String(bad));
});

test("bad entries in SP_PEOPLE are dropped, not trusted", () => {
  const env = makeEnv({ SP_PEOPLE: JSON.stringify({ father: "p@example.test", "Bad Id": "x@example.test", owner: "no-at-sign", ghost: 5, evil: "a@b.test&to=c@d.test" }) });
  assert.deepEqual(people(env), { father: "p@example.test" });
  assert.deepEqual(people({}), {});
});

test("display names", () => {
  assert.equal(displayName("father"), "Father");
  assert.equal(displayName("owner"), "Owner");
});

test("a signed session names its person until it expires", async () => {
  const now = 1_800_000_000_000;
  const value = await signSession("father", COOKIE_KEY, now);
  assert.equal(await verifySession(value, COOKIE_KEY, now), "father");
  assert.equal(await verifySession(value, COOKIE_KEY, now + (SESSION_SECONDS - 1) * 1000), "father");
  assert.equal(await verifySession(value, COOKIE_KEY, now + SESSION_SECONDS * 1000), null, "expired");
});

test("forged, tampered and swapped sessions fail", async () => {
  const now = 1_800_000_000_000;
  const value = await signSession("father", COOKIE_KEY, now);
  const [v, person, exp, sig] = value.split(".");
  const flip = sig[0] === "A" ? "B" + sig.slice(1) : "A" + sig.slice(1);
  const cases = {
    "other key": await signSession("father", "x".repeat(40), now),
    "person swapped": [v, "owner", exp, sig].join("."),
    "expiry pushed": [v, person, String(Number(exp) + 86400), sig].join("."),
    "signature flipped": [v, person, exp, flip].join("."),
    "no signature": [v, person, exp].join("."),
    "empty signature": [v, person, exp, ""].join("."),
    "wrong version": ["v2", person, exp, sig].join("."),
    "garbage": "hello",
    "empty": "",
  };
  for (const [name, forged] of Object.entries(cases)) {
    assert.equal(await verifySession(forged, COOKIE_KEY, now), null, name);
  }
});

test("a session signed far in the future is refused", async () => {
  const now = 1_800_000_000_000;
  const value = await signSession("father", COOKIE_KEY, now + 5 * 365 * 86400 * 1000);
  assert.equal(await verifySession(value, COOKIE_KEY, now), null);
});

test("a short cookie key is refused for signing and verifying", async () => {
  await assert.rejects(signSession("father", "short", Date.now()));
  assert.equal(await verifySession("v1.father.1.AAAA", "short", Date.now()), null);
});

test("sameSecret compares in constant time and handles missing values", async () => {
  assert.equal(await sameSecret("abc", "abc"), true);
  assert.equal(await sameSecret("abc", "abd"), false);
  assert.equal(await sameSecret("abc", "abcd"), false);
  assert.equal(await sameSecret(null, "abc"), false);
  assert.equal(await sameSecret("", ""), false);
});

test("safeNext keeps same-site paths and drops everything else", () => {
  assert.equal(safeNext("/kite/callback?request_token=abc"), "/kite/callback?request_token=abc");
  assert.equal(safeNext("/"), "/");
  for (const bad of [null, "", "https://evil.example/", "//evil.example", "/\\evil.example", "/login", "/login?next=/", "/login/verify?t=x", "javascript:alert(1)", "/a\nb"]) {
    assert.equal(safeNext(bad), "/", String(bad));
  }
});
