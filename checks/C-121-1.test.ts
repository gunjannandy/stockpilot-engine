// C-121-1: health returns every part and refuses without the header.

import { describe, expect, it } from "vitest";
import { makeApp } from "../api/src/testkit";
import { PARTS } from "../contract/src";

describe("C-121-1 health", () => {
  it("refuses without the secret header, and with a wrong one", async () => {
    const { app } = await makeApp();
    expect((await app.request("/api/health")).status).toBe(401);
    expect(
      (await app.request("/api/health", { headers: { "x-health-secret": "x".repeat(24) } })).status,
    ).toBe(401);
  });
  it("returns every part, amber until it beats, red when overdue or failed", async () => {
    let t = new Date("2026-11-27T10:00:00+05:30");
    const { withSecret, signed } = await makeApp({ now: () => t });
    const read = async () =>
      (await withSecret("/api/health")).json() as Promise<{
        overall: string;
        parts: { part: string; status: string; overdue: boolean }[];
      }>;
    let h = await read();
    expect(h.parts.map((p) => p.part)).toEqual([...PARTS]);
    expect(h.parts.find((p) => p.part === "job.ping")?.status).toBe("amber");
    const beat = (ok: boolean, due: string) =>
      signed("POST", "/api/heartbeat", {
        part: "job.ping",
        version: "v1",
        at: "2026-11-27T10:00:00+05:30",
        ok,
        error: ok ? null : "boom",
        next_expected_by: due,
      });
    expect((await beat(true, "2026-11-28T10:00:00+05:30")).status).toBe(200);
    h = await read();
    expect(h.parts.find((p) => p.part === "job.ping")?.status).toBe("green");
    t = new Date("2026-11-29T10:00:00+05:30");
    h = await read();
    expect(h.parts.find((p) => p.part === "job.ping")).toMatchObject({
      status: "red",
      overdue: true,
    });
    expect(h.overall).toBe("red");
    await beat(false, "2026-11-30T10:00:00+05:30");
    expect((await read()).parts.find((p) => p.part === "job.ping")?.status).toBe("red");
  });
  it("takes a heartbeat only from a signed caller and only for a known part", async () => {
    const { app, signed } = await makeApp();
    const body = {
      part: "nope",
      version: "v",
      at: "2026-11-27T10:00:00+05:30",
      ok: true,
      error: null,
      next_expected_by: null,
    };
    expect(
      (await app.request("/api/heartbeat", { method: "POST", body: JSON.stringify(body) })).status,
    ).toBe(401);
    expect((await signed("POST", "/api/heartbeat", body)).status).toBe(400);
  });
});
