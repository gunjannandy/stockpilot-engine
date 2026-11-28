// C-116-2: a button Job is dispatched at once; a dispatched Job not started within 3 minutes is dispatched again.
import { expect, it } from "vitest";
import { scheduleApp } from "../api/src/schedule/testkit";
import { queueJob } from "../api/src/schedule/tick";

const IST = (hhmm: string, day = "2026-11-26") => new Date(`${day}T${hhmm}:00+05:30`);

it("C-116-2 a press dispatches the Job the moment it is pressed", async () => {
  const t = await scheduleApp({ datasets: [], now: () => IST("10:00") });
  const res = await t.press({ kind: "analyse", subject: "ABC" });
  expect(res.status).toBe(200);
  expect(t.github.dispatched).toHaveLength(1);
  expect(t.github.dispatched[0]?.inputs).toMatchObject({
    kind: "analyse",
    subject: "ABC",
    day: "2026-11-26",
  });
  expect(await res.json()).toMatchObject({ key: "analyse|ABC|2026-11-26", status: "queued" });
});

it("C-116-2 a second press of the same Job is refused and dispatches nothing more", async () => {
  const t = await scheduleApp({ datasets: [], now: () => IST("10:00") });
  await t.press({ kind: "analyse", subject: "ABC" });
  expect((await t.press({ kind: "analyse", subject: "ABC" })).status).toBe(409);
  expect(t.github.dispatched).toHaveLength(1);
  expect((await t.press({ kind: "analyse", subject: "XYZ" })).status).toBe(200);
});

it("C-116-2 a dispatched Job not started within 3 minutes is dispatched again", async () => {
  const t = await scheduleApp({ datasets: [], now: () => IST("10:00") });
  await t.press({ kind: "analyse", subject: "ABC" });
  expect((await t.tick(IST("10:02"))).redispatched).toEqual([]);
  expect((await t.tick(IST("10:03"))).redispatched).toEqual(["analyse|ABC|2026-11-26"]);
  expect(t.github.dispatched).toHaveLength(2);
  // 3 minutes after the second dispatch, again; but not within them.
  expect((await t.tick(IST("10:05"))).redispatched).toEqual([]);
  expect((await t.tick(IST("10:06"))).redispatched).toEqual(["analyse|ABC|2026-11-26"]);
});

it("C-116-2 a Job that started is not dispatched again", async () => {
  const t = await scheduleApp({ datasets: [], now: () => IST("10:00") });
  await t.press({ kind: "analyse", subject: "ABC" });
  expect((await t.begin({ kind: "analyse", subject: "ABC", run_id: "r1" })).status).toBe(200);
  expect((await t.tick(IST("10:10"))).redispatched).toEqual([]);
  expect(t.github.dispatched).toHaveLength(1);
});

it("C-116-2 a press while GitHub refuses leaves the Job queued for the tick to dispatch", async () => {
  let refuse = true;
  const t = await scheduleApp({
    datasets: [],
    now: () => IST("10:00"),
    failDispatch: () => refuse,
  });
  expect((await t.press({ kind: "analyse", subject: "ABC" })).status).toBe(502);
  refuse = false;
  expect((await t.tick(IST("10:01"))).redispatched).toEqual(["analyse|ABC|2026-11-26"]);
});

it("C-116-2 a press needs a signed-in person, and a paused kind refuses", async () => {
  const t = await scheduleApp({ datasets: [], now: () => IST("10:00"), env: { SP_ENV: "prod" } });
  expect((await t.press({ kind: "analyse", subject: "ABC" })).status).toBe(401);
  const u = await scheduleApp({ datasets: [], now: () => IST("10:00") });
  await u.db.prepare("insert into job_pauses (kind, paused_at) values ('analyse', 'x')").run();
  expect((await u.press({ kind: "analyse", subject: "ABC" })).status).toBe(423);
});

it("C-116-2 a stuck documents Refresh is dispatched again to the private repo", async () => {
  const t = await scheduleApp({ datasets: [], now: () => IST("10:00") });
  await queueJob(t.core(IST("10:00")), { kind: "documents", subject: "drive", day: "2026-11-26" });
  expect((await t.tick(IST("10:03"))).redispatched).toEqual(["documents|drive|2026-11-26"]);
  expect(t.github.dispatched[0]).toMatchObject({
    repo: "stockpilot-hq/stockpilot",
    workflow: "documents.yml",
  });
});
