// C-001-1: a link sign-in sets a one-year host-only cookie.
import { afterEach, describe, expect, it } from "vitest";
import { FATHER, makeAuthApp } from "../api/src/auth/testkit";

let restore = () => {};
afterEach(() => restore());

describe("C-001-1 link sign-in", () => {
  it("emails one link, and spending it sets a one-year host-only cookie", async () => {
    const t = await makeAuthApp();
    restore = t.bridge.restore;
    const ask = await t.post("/login", { email: FATHER });
    expect(ask.status).toBe(200);
    expect(t.bridge.sent).toHaveLength(1);
    expect(t.bridge.sent[0]?.to).toBe(FATHER);
    const token = t.bridge.sent[0]?.token ?? "";
    // opening the link never spends it (mail scanners open links)
    expect((await t.app.request(`/login/verify?t=${token}`)).status).toBe(200);
    const res = await t.post("/login/verify", { t: token });
    expect(res.status).toBe(303);
    const set = res.headers.get("set-cookie") ?? "";
    expect(set).toMatch(/^__Host-sp=/);
    expect(set).toContain("Max-Age=31536000");
    expect(set).toContain("Path=/");
    expect(set).not.toMatch(/domain=/i);
    expect(set).toMatch(/HttpOnly/);
    // the cookie works, and the link works once
    const cookie = set.split(";")[0] as string;
    const me = await t.app.request("/api/me", { headers: { cookie } });
    expect(await me.json()).toEqual({ person: "father" });
    expect((await t.post("/login/verify", { t: token })).status).toBe(400);
  });
  it("lets the signed-in person in, and signing out clears the cookie", async () => {
    const t = await makeAuthApp();
    restore = t.bridge.restore;
    const s = await t.signIn(FATHER);
    const out = await t.app.request("/logout", {
      method: "POST",
      headers: { cookie: s?.cookie ?? "", origin: "http://localhost" },
    });
    expect(out.headers.get("set-cookie")).toContain("Max-Age=0");
  });
});
