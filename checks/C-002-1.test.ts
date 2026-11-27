// C-002-1: a third address gets no link and no session.
import { afterEach, describe, expect, it } from "vitest";
import { signSession } from "../api/src/auth/lib";
import { makeAuthApp, PROD_KEY } from "../api/src/auth/testkit";

let restore = () => {};
afterEach(() => restore());

describe("C-002-1 only two addresses", () => {
  it("answers a stranger exactly as it answers a known address, and sends nothing", async () => {
    const t = await makeAuthApp();
    restore = t.bridge.restore;
    const a = await t.post("/login", { email: "stranger@example.test" });
    const b = await t.post("/login", { email: "father@example.test" });
    expect(a.status).toBe(b.status);
    expect(await a.text()).toBe(await b.text());
    expect(t.bridge.sent.map((m) => m.to)).toEqual(["father@example.test"]);
    expect(await t.signIn("stranger@example.test")).toBeNull();
  });
  it("refuses a session for a person who is not in the list, even correctly signed", async () => {
    const t = await makeAuthApp();
    restore = t.bridge.restore;
    const value = await signSession({ SP_COOKIE_KEY: PROD_KEY }, "mallory", Date.now());
    const res = await t.app.request("/api/me", { headers: { cookie: `__Host-sp=${value}` } });
    expect(res.status).toBe(401);
  });
  it("refuses a forged or missing cookie", async () => {
    const t = await makeAuthApp();
    restore = t.bridge.restore;
    expect((await t.app.request("/api/me")).status).toBe(401);
    expect(
      (
        await t.app.request("/api/me", {
          headers: { cookie: "__Host-sp=v1.production.owner.9999999999.AAAA" },
        })
      ).status,
    ).toBe(401);
  });
});
