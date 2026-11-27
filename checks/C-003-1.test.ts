// C-003-1: a preview cookie is refused by production and the reverse.
import { afterEach, describe, expect, it } from "vitest";
import { makeAuthApp, OWNER } from "../api/src/auth/testkit";

const restores: (() => void)[] = [];
afterEach(() => {
  for (const r of restores.splice(0)) r();
});

describe("C-003-1 separate preview sign-in", () => {
  it("refuses each side's cookie on the other, under either cookie name", async () => {
    // one fake send endpoint at a time: each app signs in, then gives the global fetch back
    const prod = await makeAuthApp();
    const p = await prod.signIn(OWNER);
    prod.bridge.restore();
    const preview = await makeAuthApp({ auth: { SP_ENV: "preview" } });
    restores.push(preview.bridge.restore);
    const v = await preview.signIn(OWNER);
    expect(p?.cookie).toMatch(/^__Host-sp=/);
    expect(v?.cookie).toMatch(/^__Host-sp_preview=/);
    const value = (c?: { cookie: string }) => (c?.cookie ?? "").split("=").slice(1).join("=");
    const ask = (t: typeof prod, cookie: string) =>
      t.app.request("/api/me", { headers: { cookie } });
    expect((await ask(prod, p?.cookie ?? "")).status).toBe(200);
    expect((await ask(preview, v?.cookie ?? "")).status).toBe(200);
    for (const name of ["__Host-sp", "__Host-sp_preview"]) {
      expect((await ask(prod, `${name}=${value(v)}`)).status).toBe(401);
      expect((await ask(preview, `${name}=${value(p)}`)).status).toBe(401);
    }
  });
  it("will not let a preview reuse production's secret", async () => {
    const t = await makeAuthApp({
      auth: { SP_ENV: "preview", SP_PREVIEW_COOKIE_KEY: "p".repeat(40) },
    });
    restores.push(t.bridge.restore);
    expect((await t.post("/login", { email: OWNER })).status).toBe(503);
  });
});
