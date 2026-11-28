import { SCORE_DAYS } from "@stockpilot/contract";
import { githubFromEnv } from "../../../adapters/src/github";
import { istDay } from "../app";
import type { Duty } from "../schedule/duties";
import { dispatchJob, queueJob } from "../schedule/tick";

const addDays = (day: string, n: number) =>
  new Date(Date.parse(`${day}T00:00:00Z`) + n * 86400_000).toISOString().slice(0, 10);

/** The models duty, every hour: one bench Job per IST hour (it ends at once when the prompt, model, method and cases
 * are the ones it last scored, so only a change costs model calls), and one post-mortem Job per day when a call has
 * reached its three-month score without a post-mortem. The unique job key makes a repeat a no-op. */
export const modelsDuty: Duty = {
  id: "models",
  everyMinutes: 60,
  async run(core) {
    const github = githubFromEnv(core.env as Record<string, string | undefined>);
    if (!github) return "no bot key set: nothing dispatched";
    const day = istDay(core.now());
    const out: string[] = [];
    const bench = {
      kind: "bench",
      subject: String(
        Number(new Date(core.now().getTime() + 5.5 * 3600_000).getUTCHours()),
      ).padStart(2, "0"),
      day,
    };
    if (await queueJob(core, bench)) {
      await dispatchJob({ github }, { ...bench, range_from: day, range_to: day });
      out.push(`bench ${bench.subject} dispatched`);
    }
    const waiting = (await core.d1
      .prepare(
        "select count(*) as n from analyse_calls where call in ('buy','avoid') and day <= ? and key not in (select call_key from postmortems)",
      )
      .bind(addDays(day, -SCORE_DAYS))
      .first()) as { n: number } | null;
    const pm = { kind: "postmortem", subject: "all", day };
    if ((waiting?.n ?? 0) > 0 && (await queueJob(core, pm))) {
      await dispatchJob({ github }, { ...pm, range_from: day, range_to: day });
      out.push("postmortem dispatched");
    }
    return out.join(", ") || "nothing due";
  },
};
