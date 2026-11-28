// The Feedback cron duty: each ask's status follows its ticket (story 96) and an ask unreviewed for
// 24 hours opens one issue (story 97). Both by code through the bot, no model.
import { githubFromEnv } from "../../../adapters/src/github";
import type { Core } from "../jobs/runtime";
import type { Duty } from "../schedule/duties";
import { ctxFor, followTickets, nudgeStale } from "./feedback";

export const feedbackDuty: Duty = {
  id: "feedback",
  everyMinutes: 15,
  async run(core: Core) {
    const bot = githubFromEnv(core.env as Record<string, string | undefined>);
    if (!bot) return "no bot key set: nothing followed";
    const ctx = ctxFor(core.d1, core.now);
    const moved = await followTickets(ctx, bot);
    const nudged = await nudgeStale(ctx, bot);
    return `moved ${moved}, nudged ${nudged}`;
  },
};
