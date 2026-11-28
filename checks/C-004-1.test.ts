// C-004-1: the sixth link request in a minute is refused.
import { afterEach, describe, expect, it } from "vitest";
import { makeAuthApp } from "../api/src/auth/testkit";

let restore = () => {};
afterEach(() => restore());

describe("C-004-1 link rate limit", () => {
  it("answers five requests a minute and refuses the sixth", async () => {
    let now = new Date("2026-11-27T10:00:00+05:30");
    const t = await makeAuthApp({ now: () => now });
    restore = t.bridge.restore;
    const statuses: number[] = [];
    for (let i = 0; i < 6; i++) statuses.push((await t.post("/login", { email: `x${i}@example.test` }, { "CF-Connecting-IP": "203.0.113.9" })).status);
    expect(statuses).toEqual([200, 200, 200, 200, 200, 429]);
    // another address on the network is unaffected, and the minute ends
    expect((await t.post("/login", { email: "y@example.test" }, { "CF-Connecting-IP": "203.0.113.10" })).status).toBe(200);
    now = new Date(now.getTime() + 61_000);
    expect((await t.post("/login", { email: "z@example.test" }, { "CF-Connecting-IP": "203.0.113.9" })).status).toBe(200);
  });
  it("sends at most three links to one address in fifteen minutes", async () => {
    const t = await makeAuthApp();
    restore = t.bridge.restore;
    for (let i = 0; i < 5; i++) await t.post("/login", { email: "father@example.test" }, { "CF-Connecting-IP": `198.51.100.${i}` });
    expect(t.bridge.sent).toHaveLength(3);
  });
});
