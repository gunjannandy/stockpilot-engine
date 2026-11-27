// C-001-2: production check, run here against the real app and in production by the check runner.
import { afterEach, describe, expect, it } from "vitest";
import { makeAuthApp } from "../api/src/auth/testkit";

let restore = () => {};
afterEach(() => restore());

describe("C-001-2", () => {
  it("passes on a correctly set up app", async () => {
    const t = await makeAuthApp();
    restore = t.bridge.restore;
    const run = (await (await t.signed("POST", "/api/checks/run")).json()) as {
      results: { id: string; ok: boolean; detail: string }[];
    };
    expect(run.results.find((r) => r.id === "C-001-2")).toMatchObject({ ok: true });
  });
  it("fails when a signed-out visit is let through", async () => {
    // sign-in off (as in development) is the one setting that lets visits through; the check then says so
    const t = await makeAuthApp({ auth: { SP_ENV: "dev" } });
    restore = t.bridge.restore;
    expect((await t.app.request("/api/me")).status).toBe(200);
    const run = (await (await t.signed("POST", "/api/checks/run")).json()) as {
      results: { id: string; detail: string }[];
    };
    expect(run.results.find((r) => r.id === "C-001-2")?.detail).toContain("off in development");
  });
});
