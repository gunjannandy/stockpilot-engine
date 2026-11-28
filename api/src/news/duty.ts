import { githubFromEnv } from "../../../adapters/src/github";
import { istDay } from "../app";
import type { Duty } from "../schedule/duties";
import { dispatchJob, queueJob } from "../schedule/tick";

/** IST quarter-hour slot of `now`, like `0845`. It is the Job's subject, so each quarter has its own key. */
export function newsSlot(now: Date): string {
  const t = new Date(now.getTime() + 5.5 * 3600_000);
  const m = Math.floor(t.getUTCMinutes() / 15) * 15;
  return `${String(t.getUTCHours()).padStart(2, "0")}${String(m).padStart(2, "0")}`;
}

/** The news duty: every 15 minutes, one news Job per slot (the unique key makes a repeat a no-op). */
export const newsDuty: Duty = {
  id: "news",
  everyMinutes: 15,
  async run(core) {
    const github = githubFromEnv(core.env as Record<string, string | undefined>);
    if (!github) return "no bot key set: nothing dispatched";
    const job = { kind: "news", subject: newsSlot(core.now()), day: istDay(core.now()) };
    if (!(await queueJob(core, job))) return `news ${job.subject} already queued`;
    await dispatchJob({ github }, { ...job, range_from: job.day, range_to: job.day });
    return `news ${job.subject} dispatched`;
  },
};
