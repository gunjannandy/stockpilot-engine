import { describe, expect, it } from "vitest";
import { makeApp } from "../testkit";

describe("layout row", () => {
  it("is empty until the owner writes it, then comes back as written; bad bodies and strangers are refused", async () => {
    const { app, withSecret } = await makeApp();
    expect(await (await app.request("/api/layout")).json()).toEqual({ layout: null });
    const body = { rail: ["funds", "today"], hidden: ["admin"] };
    expect(
      (await app.request("/api/layout", { method: "PUT", body: JSON.stringify(body) })).status,
    ).toBe(401);
    expect(
      (await withSecret("/api/layout", { method: "PUT", body: JSON.stringify({ rail: "x" }) }))
        .status,
    ).toBe(400);
    expect(
      (await withSecret("/api/layout", { method: "PUT", body: JSON.stringify(body) })).status,
    ).toBe(200);
    expect(await (await app.request("/api/layout")).json()).toEqual({ layout: body });
  });
});
