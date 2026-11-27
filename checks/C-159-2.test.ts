// C-159-2: after each promotion the check runner stores every production check's result, shown on health.
import { describe, expect, it } from "vitest";
import { makeApp } from "../api/src/testkit";

describe("C-159-2 the check runner stores every result", () => {
  it("stores one result per registered production check, last one auditing the rest", async () => {
    const { registry, signed, withSecret } = await makeApp();
    const ids = registry.areas
      .flatMap((a) => a.checks ?? [])
      .map((k) => k.id)
      .sort();
    expect(ids).toEqual(expect.arrayContaining(["C-121-1", "C-135-1", "C-137-1", "C-159-2"]));
    const run = (await (await signed("POST", "/api/checks/run")).json()) as {
      results: { id: string; ok: boolean; detail: string }[];
    };
    expect(run.results.map((r) => r.id).sort()).toEqual(ids);
    expect(run.results.at(-1)?.id).toBe("C-159-2");
    expect(run.results.filter((r) => !r.ok)).toEqual([]);
    const health = (await (await withSecret("/api/health")).json()) as {
      checks: { id: string }[];
      parts: { part: string; status: string }[];
    };
    expect(health.checks.map((c) => c.id).sort()).toEqual(ids);
    expect(health.parts.find((p) => p.part === "check_runner")?.status).toBe("green");
  });
  it("records a crashing check as red instead of stopping the run", async () => {
    const { registry, signed, withSecret } = await makeApp();
    registry.areas.push({
      name: "boom",
      checks: [
        {
          id: "C-999-1",
          run: async () => {
            throw new Error("nope");
          },
        },
      ],
    });
    const run = (await (await signed("POST", "/api/checks/run")).json()) as {
      results: { id: string; ok: boolean }[];
    };
    expect(run.results.find((r) => r.id === "C-999-1")?.ok).toBe(false);
    expect(run.results.length).toBeGreaterThan(4);
    const health = (await (await withSecret("/api/health")).json()) as { overall: string };
    expect(health.overall).toBe("red");
  });
  it("refuses an unsigned caller", async () => {
    const { app } = await makeApp();
    expect((await app.request("/api/checks/run", { method: "POST" })).status).toBe(401);
  });
});
