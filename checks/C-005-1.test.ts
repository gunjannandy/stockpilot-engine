// C-005-1: owner-only writes are refused for the father.
import { afterEach, describe, expect, it } from "vitest";
import { FATHER, makeAuthApp, OWNER } from "../api/src/auth/testkit";

let restore = () => {};
afterEach(() => restore());

describe("C-005-1 owner-only writes", () => {
  it("lets the owner write, refuses the father and a stranger", async () => {
    const t = await makeAuthApp();
    restore = t.bridge.restore;
    const owner = await t.signIn(OWNER);
    const father = await t.signIn(FATHER, { "CF-Connecting-IP": "198.51.100.7" });
    const write = (cookie?: string) =>
      t.app.request("/api/me/owner-probe", {
        method: "POST",
        headers: { ...(cookie ? { cookie } : {}), origin: "http://localhost" },
      });
    expect((await write(owner?.cookie)).status).toBe(200);
    expect((await write(father?.cookie)).status).toBe(403);
    expect((await write()).status).toBe(401);
  });
  it("refuses a cookie-carrying write that comes from another site", async () => {
    const t = await makeAuthApp();
    restore = t.bridge.restore;
    const owner = await t.signIn(OWNER);
    const res = await t.app.request("/api/me/owner-probe", {
      method: "POST",
      headers: { cookie: owner?.cookie ?? "", origin: "https://evil.example" },
    });
    expect(res.status).toBe(403);
  });
  it("puts sign-in in front of the shared person guard", async () => {
    const t = await makeAuthApp();
    restore = t.bridge.restore;
    expect((await t.app.request("/api/ping")).status).toBe(401);
    const s = await t.signIn(FATHER);
    expect(
      (await t.app.request("/api/ping", { headers: { cookie: s?.cookie ?? "" } })).status,
    ).toBe(200);
  });
});
