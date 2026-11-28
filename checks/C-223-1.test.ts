// LO223: backup and drill heartbeats are watched parts: accepted, shown on health, red when they fail.
import { expect, it } from "vitest";
import { makeApp } from "../api/src/testkit";
import { PARTS } from "../contract/src";

it("LO223 job.backup and job.drill are watched and beat", async () => {
  expect(PARTS).toContain("job.backup");
  expect(PARTS).toContain("job.drill");
  const { withSecret, signed } = await makeApp({ now: () => new Date("2026-11-27T10:00:00+05:30") });
  for (const part of ["job.backup", "job.drill"]) {
    const r = await signed("POST", "/api/heartbeat", {
      part, version: "v1", at: "2026-11-27T10:00:00+05:30", ok: false, error: "boom", next_expected_by: null,
    });
    expect(r.status).toBe(200);
  }
  const h = (await (await withSecret("/api/health")).json()) as { parts: { part: string; status: string }[] };
  for (const part of ["job.backup", "job.drill"])
    expect(h.parts.find((p) => p.part === part)?.status).toBe("red");
});
