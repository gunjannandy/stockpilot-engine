import { CONTRACT_HEADER, CONTRACT_VERSION } from "@stockpilot/contract";
import { describe, expect, it } from "vitest";
import { makeApp } from "../testkit";

describe("contract version header", () => {
  it("rides on every answer: ok, refused and not found", async () => {
    const { app } = await makeApp();
    for (const path of ["/api/ping", "/api/no-such-route"]) {
      const res = await app.request(path);
      expect(res.headers.get(CONTRACT_HEADER)).toBe(CONTRACT_VERSION);
    }
  });
});
