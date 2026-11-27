// C-129-1: past the daily cap a model Job is refused and the pane says next update tomorrow; a repeat brief returns the cached answer.
import { expect, it } from "vitest";
import { jobsApp } from "../api/src/jobs/testkit";

const ask = (t: Awaited<ReturnType<typeof jobsApp>>, brief: string, kind = "analyse") =>
  t.signed("POST", "/api/model/claim", { kind, model: "haiku", brief_hash: brief });

it("C-129-1 past the daily cap a model Job is refused and the status says next update tomorrow", async () => {
  const t = await jobsApp({ caps: { analyse: 2 } });
  expect(await (await ask(t, "b1")).json()).toMatchObject({ cached: false, left: 1 });
  expect(await (await ask(t, "b2")).json()).toMatchObject({ cached: false, left: 0 });
  const refused = await ask(t, "b3");
  expect(refused.status).toBe(429);
  expect(await refused.json()).toMatchObject({ error: "daily cap reached", message: "Next update tomorrow" });
  const s = await t.app.request("/api/model/status?kind=analyse");
  expect(await s.json()).toMatchObject({ used: 2, cap: 2, left: 0, message: "Next update tomorrow" });
});

it("C-129-1 a repeat brief returns the cached answer and costs nothing", async () => {
  const t = await jobsApp({ caps: { analyse: 1 } });
  expect((await ask(t, "same")).status).toBe(200);
  const stored = await t.signed("POST", "/api/model/answer", {
    kind: "analyse",
    model: "haiku",
    brief_hash: "same",
    answer: "Hold.",
  });
  expect(stored.status).toBe(200);
  // The cap of one is spent, yet the same brief is answered from the cache, as often as asked.
  for (let i = 0; i < 3; i++) {
    const again = await ask(t, "same");
    expect(again.status).toBe(200);
    expect(await again.json()).toEqual({ cached: true, answer: "Hold." });
  }
  const s = await (await t.app.request("/api/model/status?kind=analyse")).json();
  expect(s).toMatchObject({ used: 1, left: 0 });
});

it("C-129-1 the cache is keyed by model and by day, and the cap resets tomorrow", async () => {
  let now = new Date("2026-11-27T05:00:00Z");
  const t = await jobsApp({ caps: { analyse: 1 }, now: () => now });
  await ask(t, "x");
  await t.signed("POST", "/api/model/answer", { kind: "analyse", model: "haiku", brief_hash: "x", answer: "A" });
  const other = await t.signed("POST", "/api/model/claim", { kind: "analyse", model: "sonnet", brief_hash: "x" });
  expect(other.status).toBe(429); // another model is a different key, so it is a fresh ask and the cap is spent
  now = new Date("2026-11-28T05:00:00Z");
  expect(await (await ask(t, "x")).json()).toMatchObject({ cached: false }); // new day: no cache, new cap
});

it("C-129-1 only the Jobs' signed calls reach the gate, and unknown kinds are refused", async () => {
  const t = await jobsApp();
  expect((await t.app.request("/api/model/claim", { method: "POST", body: "{}" })).status).toBe(401);
  expect((await ask(t, "b", "not_a_kind")).status).toBe(400);
});
