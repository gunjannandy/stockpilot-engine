// C-131-1: the bench scores after a prompt or model change (its report is stored with the fingerprint it scored); a red
// report pauses releases, and a green one lifts only a pause the bench itself set.
import type { BenchReport } from "@stockpilot/contract";
import { expect, it } from "vitest";
import { makeApp } from "../api/src/testkit";

const report = (over: Partial<BenchReport> = {}): BenchReport => ({
  fingerprint: "fp1",
  model: "haiku",
  scores: { n: 30, form_ok: 30, form_rate: 1, hit_rate: 0.6, decided: 14, code_hit_rate: 0.55 },
  problems: {},
  comparison: { form_rate: 1, agreement: 0.9, passed: true, forecast_model: "haiku" },
  forecast_model: "haiku",
  red: [],
  ...over,
});

const paused = async (t: Awaited<ReturnType<typeof makeApp>>) =>
  ((await (await t.app.request("/api/flags")).json()) as { flags: Record<string, boolean> }).flags
    .pause_releases === true;

it("C-131-1 a red bench pauses releases and a green one lifts its own pause", async () => {
  const t = await makeApp();
  expect(await paused(t)).toBe(false);
  expect(
    (
      await t.signed(
        "POST",
        "/api/bench/report",
        report({ red: ["form checks 80% are under 95%"] }),
      )
    ).status,
  ).toBe(200);
  expect(await paused(t)).toBe(true);
  expect((await t.signed("POST", "/api/bench/report", report({ fingerprint: "fp2" }))).status).toBe(
    200,
  );
  expect(await paused(t)).toBe(false);
});

it("C-131-1 a green bench never lifts a pause the owner set", async () => {
  const t = await makeApp();
  await paused(t); // first request creates the tables
  await t.db
    .prepare("insert into flags (key, enabled, updated_at) values ('pause_releases', 1, 'x')")
    .run();
  await t.signed("POST", "/api/bench/report", report());
  expect(await paused(t)).toBe(true);
});

it("C-131-1 the status gives the Job the fingerprint it last scored and the comparison", async () => {
  const t = await makeApp();
  expect(await (await t.signed("GET", "/api/bench/status")).json()).toMatchObject({
    fingerprint: null,
    comparison: null,
  });
  await t.signed("POST", "/api/bench/report", report());
  const s = (await (await t.signed("GET", "/api/bench/status")).json()) as {
    fingerprint: string;
    forecast_model: string;
  };
  expect(s.fingerprint).toBe("fp1");
  expect(s.forecast_model).toBe("haiku");
});
