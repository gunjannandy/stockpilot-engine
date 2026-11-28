import { expect, it } from "vitest";
import { passOn } from "../../../frontdoor/_worker.js";
import { authEnv, makeAuthApp, OWNER } from "./testkit";

const APP = "https://app.example.test";

it("Front door: path, query, method and body go through; cookies and Location come back right", async () => {
  let seen: Request | undefined;
  const fetcher = async (req: Request) => {
    seen = req;
    return new Response("body", {
      status: 303,
      headers: [
        ["location", `${APP}/sync?synced=1#x`],
        ["set-cookie", "__Host-sp=a; Path=/; Secure"],
        ["set-cookie", "other=b; Path=/"],
      ],
    });
  };
  const res = await passOn(
    new Request("https://front.example.test/kite/callback?request_token=t&status=success", {
      method: "POST",
      headers: {
        cookie: "__Host-sp=v",
        "cf-connecting-ip": "1.2.3.4",
        "x-forwarded-host": "evil.test",
      },
      body: "a=1",
    }),
    { APP_ORIGIN: APP },
    fetcher as typeof fetch,
  );
  expect(seen?.url).toBe(`${APP}/kite/callback?request_token=t&status=success`);
  expect(seen?.method).toBe("POST");
  expect(seen?.redirect).toBe("manual");
  expect(await seen?.text()).toBe("a=1");
  expect(seen?.headers.get("cookie")).toBe("__Host-sp=v");
  expect(seen?.headers.get("x-forwarded-host")).toBeNull();
  expect(res.status).toBe(303);
  expect(res.headers.get("location")).toBe("/sync?synced=1#x");
  expect(res.headers.getSetCookie()).toHaveLength(2);
});

it("Front door: another site's redirect (Kite) is left alone, and a dead App gives 502", async () => {
  const kite = "https://kite.example.test/connect/login?v=3";
  const res = await passOn(
    new Request("https://front.example.test/kite/login"),
    { APP_ORIGIN: APP },
    (async () => new Response(null, { status: 302, headers: { location: kite } })) as typeof fetch,
  );
  expect(res.headers.get("location")).toBe(kite);
  const down = await passOn(
    new Request("https://front.example.test/"),
    { APP_ORIGIN: APP },
    (async () => {
      throw new Error("down");
    }) as typeof fetch,
  );
  expect(down.status).toBe(502);
});

it("Sign-in behind the front door: the emailed link and the form check use the public address", async () => {
  const front = "https://front.example.test";
  const t = await makeAuthApp({ auth: authEnv({ SITE_URL: `${front}/some/path` }) });
  const bridge = globalThis.fetch;
  let base = "";
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    base = new URL(String(input)).searchParams.get("base") ?? "";
    return bridge(input, init);
  }) as typeof fetch;
  try {
    const signed = await t.signIn(OWNER);
    expect(base).toBe(front);
    const logout = (origin: string) =>
      t.app.request("/logout", {
        method: "POST",
        headers: { cookie: signed?.cookie ?? "", origin },
      });
    expect((await logout("https://evil.example.test")).status).toBe(403);
    expect((await logout(front)).status).toBeLessThan(400);
  } finally {
    globalThis.fetch = bridge;
    t.bridge.restore();
  }
});

it("Without SITE_URL the link uses the request's own address", async () => {
  const t = await makeAuthApp();
  try {
    const res = await t.app.request("http://local.example.test/login", {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ email: OWNER }).toString(),
    });
    expect(res.status).toBe(200);
  } finally {
    t.bridge.restore();
  }
});
