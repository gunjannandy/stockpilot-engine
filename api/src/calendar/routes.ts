// The calendar's routes: the day's market status for Python and the Worker's own duties, and the
// calendar's health. The rows are the `calendar` dataset's current run (posted by the calendar Job).
import {
  CALENDAR_MIN_DAYS_AHEAD,
  type CalendarRow,
  type CalendarStatus,
  calendarEntry,
  IsoDate,
} from "@stockpilot/contract";
import { Hono } from "hono";
import { type Ctx, istDay } from "../app";
import { type Calendar, daysCovered, isTradingDay } from "./calendar";

/** The current calendar: the rows of the `calendar` dataset's current run, or an empty calendar. */
export async function loadCalendar(ctx: Pick<Ctx, "d1">): Promise<Calendar> {
  const p = (await ctx.d1
    .prepare("select run_id from pointers where dataset = 'calendar'")
    .first()) as { run_id: string } | null;
  if (!p) return { rows: [] };
  const r = (await ctx.d1
    .prepare("select body from dataset_rows where dataset = 'calendar' and run_id = ? order by seq")
    .bind(p.run_id)
    .all()) as { results: { body: string }[] };
  const entries = r.results.map((x) => calendarEntry(JSON.parse(x.body) as CalendarRow));
  return { rows: entries.filter((e) => e !== null) };
}

export function calendarStatus(cal: Calendar, today: string): CalendarStatus {
  const { until, ahead } = daysCovered(cal, today);
  const low = ahead < CALENDAR_MIN_DAYS_AHEAD;
  return {
    status: low ? "amber" : "green",
    covered_until: until,
    days_ahead: ahead,
    message: low
      ? `The market calendar covers only ${Math.max(ahead, 0)} days ahead (it should cover ${CALENDAR_MIN_DAYS_AHEAD}).`
      : `The market calendar covers ${ahead} days ahead.`,
  };
}

// The one /api/market/status: it knows the holidays.
export default function routes(ctx: Ctx) {
  const app = new Hono();

  app.get("/api/market/status", ctx.guard.ingest, async (c) => {
    const asked = c.req.query("date");
    const date = asked && IsoDate.safeParse(asked).success ? asked : istDay(ctx.now());
    return c.json({ date, ...isTradingDay(await loadCalendar(ctx), date) });
  });

  app.get("/api/calendar/status", ctx.guard.secret, async (c) =>
    c.json(calendarStatus(await loadCalendar(ctx), istDay(ctx.now()))),
  );

  return app;
}
