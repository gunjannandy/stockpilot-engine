// C-116-1: the 5-minute tick dispatches each due Job once and none on a market holiday.
import { expect, it } from "vitest";
import { scheduleApp } from "../api/src/schedule/testkit";

const IST = (hhmm: string, day = "2026-11-26") => new Date(`${day}T${hhmm}:00+05:30`);

it("C-116-1 before its time nothing is dispatched, after it the Job is dispatched once", async () => {
  const t = await scheduleApp();
  expect(await t.tick(IST("08:30"))).toMatchObject({ dispatched: [] });
  expect((await t.tick(IST("09:05"))).dispatched).toEqual(["ping|morning|2026-11-26"]);
  // The Job starts; from then on no tick dispatches it again.
  expect(
    (await t.begin({ kind: "ping", subject: "morning", day: "2026-11-26", run_id: "r1" })).status,
  ).toBe(200);
  for (const m of ["09:10", "09:15", "11:00"])
    expect((await t.tick(IST(m))).dispatched).toEqual([]);
  expect(t.github.dispatched).toHaveLength(1);
  expect(t.github.dispatched[0]).toEqual({
    repo: "stockpilot-hq/stockpilot-engine",
    workflow: "ping.yml",
    ref: "main",
    inputs: {
      kind: "ping",
      subject: "morning",
      day: "2026-11-26",
      from: "2026-11-26",
      to: "2026-11-26",
    },
  });
});

it("C-116-1 a trading-day Job is not dispatched on a market holiday or a weekend", async () => {
  const t = await scheduleApp({ withDaily: true });
  await t.setCalendar([{ id: "h", kind: "holiday", date: "2026-11-26", reason: "Holiday" }]);
  // The every-day Job (the calendar) runs on a holiday; the trading-day Job does not.
  expect((await t.tick(IST("09:05"))).dispatched).toEqual(["calendar|calendar|2026-11-26"]);
  expect((await t.tick(IST("12:00", "2026-11-28"))).dispatched).toEqual([
    "calendar|calendar|2026-11-28",
  ]); // Saturday
});

it("C-116-1 a paused kind is not dispatched", async () => {
  const t = await scheduleApp();
  await t.db.prepare("insert into job_pauses (kind, paused_at) values ('ping', 'x')").run();
  await t.tick(IST("09:05"));
  expect(t.github.dispatched).toHaveLength(0);
});

it("C-116-1 a failed Job is dispatched again when its backoff is over, and not before", async () => {
  const t = await scheduleApp();
  await t.tick(IST("09:05"));
  await t.begin({ kind: "ping", subject: "morning", day: "2026-11-26", run_id: "r1" });
  const key = "ping|morning|2026-11-26";
  await t.fail(key, "2026-11-26T09:10:00+05:30", "source down", 1);
  expect((await t.tick(IST("09:09"))).retried).toEqual([]);
  expect((await t.tick(IST("09:11"))).retried).toEqual([key]);
  expect(t.github.dispatched).toHaveLength(2);
  expect((await t.tick(IST("09:16"))).retried).toEqual([]);
});

it("C-116-1 a Job that ran out of tries is left for a person", async () => {
  const t = await scheduleApp();
  await t.tick(IST("09:05"));
  await t.begin({ kind: "ping", subject: "morning", day: "2026-11-26", run_id: "r1" });
  await t.fail("ping|morning|2026-11-26", null, "source down", 3);
  await t.tick(IST("12:00"));
  expect(t.github.dispatched).toHaveLength(1);
});
