// What is due now: a pure function of the dataset registry, the market calendar, the clock and the
// Jobs already keyed today. No I/O, so the tick's decisions are testable on their own.
import type { Dataset } from "@stockpilot/contract";
import { istDay } from "../app";
import { type Calendar, isTradingDay } from "../calendar/calendar";

export type Due = { kind: string; subject: string; day: string; key: string };

const istMinutes = (now: Date) => {
  const t = new Date(now.getTime() + 5.5 * 3600 * 1000);
  return t.getUTCHours() * 60 + t.getUTCMinutes();
};
const atMinutes = (hhmm: string) => {
  const [h, m] = hhmm.split(":").map(Number);
  return (h ?? 0) * 60 + (m ?? 0);
};

/** Jobs whose scheduled time has come today (IST), on a day they run, and that have no key yet. */
export function dueRuns(a: {
  datasets: Record<string, Dataset>;
  calendar: Calendar;
  now: Date;
  keys: Set<string>;
}): Due[] {
  const day = istDay(a.now);
  const open = isTradingDay(a.calendar, day).is_trading_day;
  const out = new Map<string, Due>();
  for (const ds of Object.values(a.datasets)) {
    if (!ds.run) continue;
    if (ds.run.on === "trading" && !open) continue;
    // From its time on, all day: a tick missed at 07:00 still starts the Job at 07:05 or the next one.
    if (istMinutes(a.now) < atMinutes(ds.run.at)) continue;
    const key = `${ds.job}|${ds.name}|${day}`;
    if (!a.keys.has(key)) out.set(key, { kind: ds.job, subject: ds.name, day, key });
  }
  return [...out.values()].sort((x, y) => x.key.localeCompare(y.key));
}
