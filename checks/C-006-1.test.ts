// C-006-1: production check, run here against the real app and in production by the check runner.
import { afterEach, describe, expect, it } from "vitest";
import { makeAuthApp } from "../api/src/auth/testkit";

let restore = () => {};
afterEach(() => restore());

describe("C-006-1", () => {
  it("passes on a correctly set up app", async () => {
    const t = await makeAuthApp();
    restore = t.bridge.restore;
    const run = (await (await t.signed("POST", "/api/checks/run")).json()) as {
      results: { id: string; ok: boolean; detail: string }[];
    };
    expect(run.results.find((r) => r.id === "C-006-1")).toMatchObject({ ok: true });
  });
  it("fails when sign-in is not set up", async () => {
    const t = await makeAuthApp({ auth: { SP_PEOPLE: "", SP_COOKIE_KEY: "" } });
    restore = t.bridge.restore;
    const run = (await (await t.signed("POST", "/api/checks/run")).json()) as {
      results: { id: string; ok: boolean }[];
    };
    expect(run.results.find((r) => r.id === "C-006-1")?.ok).toBe(false);
  });
});
