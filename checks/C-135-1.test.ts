// C-135-1: running versions match production after each release.
import { describe, expect, it } from "vitest";
import { makeApp } from "../api/src/testkit";

const beat = (version: string, at: string) => ({
  part: "job.ping", version, at, ok: true, error: null, next_expected_by: null,
});

describe("C-135-1 versions match production", () => {
  it("passes when parts that beat since the release run the release", async () => {
    const t = new Date("2026-11-27T10:00:00+05:30");
    const { signed } = await makeApp({ version: "abc123", now: () => t });
    await signed("POST", "/api/heartbeat", beat("abc123", "2026-11-27T10:05:00+05:30"));
    const run = await (await signed("POST", "/api/checks/run")).json() as { results: { id: string; ok: boolean; detail: string }[] };
    expect(run.results.find((r) => r.id === "C-135-1")).toMatchObject({ ok: true });
  });
  it("fails when a part that beat after the release reports another version", async () => {
    const t = new Date("2026-11-27T10:00:00+05:30");
    const { signed } = await makeApp({ version: "abc123", now: () => t });
    await signed("POST", "/api/heartbeat", beat("old999", "2026-11-27T10:05:00+05:30"));
    const run = await (await signed("POST", "/api/checks/run")).json() as { results: { id: string; ok: boolean; detail: string }[] };
    const r = run.results.find((x) => x.id === "C-135-1");
    expect(r?.ok).toBe(false);
    expect(r?.detail).toContain("old999");
  });
  it("ignores a part whose last beat came before this release", async () => {
    const t = new Date("2026-11-27T10:00:00+05:30");
    const { signed } = await makeApp({ version: "abc123", now: () => t });
    await signed("POST", "/api/heartbeat", beat("old999", "2026-11-26T10:05:00+05:30"));
    const run = await (await signed("POST", "/api/checks/run")).json() as { results: { id: string; ok: boolean }[] };
    expect(run.results.find((x) => x.id === "C-135-1")?.ok).toBe(true);
  });
});
