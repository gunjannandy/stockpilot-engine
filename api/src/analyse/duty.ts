import { githubFromEnv } from "../../../adapters/src/github";
import { istDay } from "../app";
import type { Duty } from "../schedule/duties";
import { dispatchJob, queueJob } from "../schedule/tick";

/** The bench duty: every hour, one bench Job per IST hour (the unique key makes a repeat a no-op). The Job ends at
 * once when the prompt, model, method and cases are the ones it last scored, so only a change costs model calls. */
export const benchDuty: Duty = {
  id: "bench",
  everyMinutes: 60,
  async run(core) {
    const github = githubFromEnv(core.env as Record<string, string | undefined>);
    if (!github) return "no bot key set: nothing dispatched";
    const now = new Date(core.now().getTime() + 5.5 * 3600_000);
    const job = {
      kind: "bench",
      subject: String(now.getUTCHours()).padStart(2, "0"),
      day: istDay(core.now()),
    };
    if (!(await queueJob(core, job))) return `bench ${job.subject} already queued`;
    await dispatchJob({ github }, { ...job, range_from: job.day, range_to: job.day });
    return `bench ${job.subject} dispatched`;
  },
};
