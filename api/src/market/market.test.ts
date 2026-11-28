import { IndicesResponse } from "@stockpilot/contract";
import { describe, expect, it } from "vitest";
import { makeApp } from "../testkit";

describe("GET /api/market/indices (stub)", () => {
  it("answers the contract's shape with nothing in it", async () => {
    const { app } = await makeApp();
    const r = await app.request("/api/market/indices");
    expect(r.status).toBe(200);
    expect(IndicesResponse.parse(await r.json())).toEqual({ as_of: null, indices: [] });
  });
});
