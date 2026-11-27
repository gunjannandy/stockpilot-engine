// C-155-2: /api/status answers without a secret, carries check results and budget percentages,
// and no private value.
import { describe, expect, it } from "vitest";
import { HEALTH, KEY, makeApp } from "../api/src/testkit";

describe("C-155-2 status", () => {
  it("answers with no secret and carries check results and budget percentages", async () => {
    const { app, signed } = await makeApp();
    const row = (n: number) => ({ id: `r${n}`, at: "2026-11-27T10:00:00+05:30", source: "job" });
    await signed("POST", "/api/ingest", {
      dataset: "ping",
      run_id: "ping-1",
      rows: [row(1), row(2)],
    });
    await signed("POST", "/api/checks/run");
    const res = await app.request("/api/status");
    expect(res.status).toBe(200);
    const s = (await res.json()) as {
      paused: boolean;
      checks: Record<string, { ok: boolean }>;
      budgets: Record<string, { used: number; limit: number; percent: number }>;
    };
    expect(Object.keys(s.checks)).toEqual(
      expect.arrayContaining(["C-121-1", "C-135-1", "C-159-2"]),
    );
    expect(s.budgets.ping?.used).toBe(2);
    expect(s.budgets.ping?.percent).toBe(1);
    expect(s.paused).toBe(false);
  });
  it("carries no secret, no row and no check detail", async () => {
    const { app, signed } = await makeApp();
    await signed("POST", "/api/ingest", {
      dataset: "ping",
      run_id: "ping-1",
      rows: [{ id: "private-marker", at: "2026-11-27T10:00:00+05:30", source: "job" }],
    });
    await signed("POST", "/api/checks/run");
    const text = await (await app.request("/api/status")).text();
    for (const secret of [KEY, HEALTH, "private-marker", "detail"])
      expect(text).not.toContain(secret);
  });
  it("shows a paused release flag", async () => {
    const { app, withSecret } = await makeApp();
    await withSecret("/api/flags", {
      method: "POST",
      body: JSON.stringify({ key: "pause_releases", enabled: true }),
    });
    expect(((await (await app.request("/api/status")).json()) as { paused: boolean }).paused).toBe(
      true,
    );
  });
});
