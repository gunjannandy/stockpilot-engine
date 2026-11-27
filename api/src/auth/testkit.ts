// Test helpers for the sign-in checks: the real app with two people configured, a fake send endpoint
// that records the emailed token, and a one-call sign-in that returns the cookie.

import type { Env } from "../app";
import { makeApp } from "../testkit";
import type { AuthEnv } from "./lib";

export const OWNER = "owner@example.test";
export const FATHER = "father@example.test";
export const PROD_KEY = "p".repeat(40);
export const PREVIEW_KEY = "v".repeat(40);

export const authEnv = (over: AuthEnv = {}): AuthEnv => ({
  SP_PEOPLE: JSON.stringify({ owner: OWNER, father: FATHER }),
  SP_ENV: undefined,
  SP_COOKIE_KEY: PROD_KEY,
  SP_PREVIEW_COOKIE_KEY: PREVIEW_KEY,
  GOOGLE_BRIDGE_URL: "https://bridge.example.test/exec",
  GOOGLE_BRIDGE_KEY: "bridge-key-0123456789",
  ...over,
});

/** Replaces global fetch with a send endpoint that records `{to, token}` and answers {ok: true}. */
export function fakeBridge() {
  const sent: { to: string; token: string }[] = [];
  const real = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const u = new URL(String(input));
    sent.push({ to: u.searchParams.get("to") ?? "", token: u.searchParams.get("t") ?? "" });
    return Response.json({ ok: true });
  }) as typeof fetch;
  return {
    sent,
    restore: () => {
      globalThis.fetch = real;
    },
  };
}

export async function makeAuthApp(
  opts: {
    auth?: AuthEnv;
    now?: () => Date;
    db?: Parameters<typeof makeApp>[0] extends infer O
      ? O extends { db?: infer D }
        ? D
        : never
      : never;
  } = {},
) {
  const t = await makeApp({
    env: authEnv(opts.auth) as unknown as Env,
    now: opts.now,
    db: opts.db,
  });
  const bridge = fakeBridge();
  const post = (path: string, form: Record<string, string>, headers: Record<string, string> = {}) =>
    t.app.request(path, {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded", ...headers },
      body: new URLSearchParams(form).toString(),
    });
  /** Asks for a link, spends it, and returns the `name=value` cookie pair. */
  async function signIn(email: string, headers: Record<string, string> = {}) {
    const before = bridge.sent.length;
    await post("/login", { email }, headers);
    const mail = bridge.sent[before];
    if (!mail) return null;
    const res = await post("/login/verify", { t: mail.token });
    const set = res.headers.get("set-cookie");
    return set ? { cookie: set.split(";")[0] as string, set } : null;
  }
  return { ...t, bridge, post, signIn };
}
