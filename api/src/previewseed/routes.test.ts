import { describe, expect, it } from "vitest";
import { makeApp } from "../testkit";

describe("previewseed route", () => {
  it("reseeds on a preview and is not there on production", async () => {
    const prod = await makeApp();
    expect((await prod.signed("POST", "/api/previewseed/reseed", {})).status).toBe(404);
    const prev = await makeApp({
      env: { SP_ENV: "preview", PRODUCTION_URL: "https://x.invalid" } as never,
    });
    const res = await prev.signed("POST", "/api/previewseed/reseed", {});
    expect(res.status).toBe(200);
    expect(((await res.json()) as { seeded: unknown[] }).seeded.length).toBeGreaterThan(0);
    const unsigned = await prev.app.request("/api/previewseed/reseed", { method: "POST" });
    expect(unsigned.status).toBe(401);
  });
});
