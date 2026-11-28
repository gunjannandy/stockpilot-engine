import { githubFromEnv } from "../../../adapters/src/github";
import { istDay } from "../app";
import { marketOpen } from "../quotes/quotes";
import type { Duty } from "../schedule/duties";
import { dispatchJob, queueJob } from "../schedule/tick";

/** IST half-hour slot of `now`, like `0930`: the Job's subject, so each half hour has its own key. */
export function listsSlot(now: Date): string {
  const t = new Date(now.getTime() + 5.5 * 3600_000);
  const m = Math.floor(t.getUTCMinutes() / 30) * 30;
  return `${String(t.getUTCHours()).padStart(2, "0")}${String(m).padStart(2, "0")}`;
}

/** The lists duty: every 30 minutes in market hours, one lists Job per slot (so "busy today" stays current). */
export const listsDuty: Duty = {
  id: "lists",
  everyMinutes: 30,
  async run(core) {
    if (!marketOpen(core.now())) return "market closed: nothing started";
    const github = githubFromEnv(core.env as Record<string, string | undefined>);
    if (!github) return "no bot key set: nothing dispatched";
    const job = { kind: "lists", subject: listsSlot(core.now()), day: istDay(core.now()) };
    if (!(await queueJob(core, job))) return `lists ${job.subject} already queued`;
    await dispatchJob({ github }, { ...job, range_from: job.day, range_to: job.day });
    return `lists ${job.subject} dispatched`;
  },
};
