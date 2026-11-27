// The cron duties this ticket owns: the watcher (with post-deploy smoke), the daily promises, the dependency checks.

import { platformFromEnv } from "../../../adapters/src/cloudflare";
import { githubFromEnv } from "../../../adapters/src/github";
import { checkDeps } from "../deps/deps";
import type { Core } from "../jobs/runtime";
import { callReseed } from "../previewseed/call";
import { storePromises } from "../promises/promises";
import type { Duty } from "../schedule/duties";
import { smoke, watch } from "./watcher";

const envOf = (c: Core) => c.env as Record<string, string | undefined>;

/**
 * One duty every 15 minutes (the registry's set of duties is fixed by C-116-3): the watcher and smoke each
 * time; the promises in the first quarter of each hour; the dependency checks every sixth hour.
 */
export const watcherDuty: Duty = {
  id: "watcher",
  everyMinutes: 15,
  async run(c) {
    const github = githubFromEnv(envOf(c));
    if (!github) return "no bot key set: nothing watched";
    const parts: string[] = [];
    const w = await watch(c, github);
    parts.push(`${w.red} red, opened ${w.opened.length}`);
    const platform = platformFromEnv(envOf(c));
    if (platform) parts.push(`smoke: ${(await smoke(c, { github, platform })).why}`);
    const ist = new Date(c.now().getTime() + 5.5 * 3600_000);
    const first = ist.getUTCMinutes() < 15;
    if (first) {
      await storePromises(c, { siteUrl: envOf(c).SITE_URL });
      parts.push("promises stored");
      if (ist.getUTCHours() % 6 === 0) parts.push(`deps ${(await checkDeps(c)).length} checked`);
    }
    // Nightly at 03:00 IST (first quarter of the hour): reseed the preview database. A failure is noted, not fatal.
    if (first && ist.getUTCHours() === 3) {
      parts.push(
        await callReseed(envOf(c)).catch(
          (e) => `reseed failed: ${e instanceof Error ? e.message : e}`,
        ),
      );
    }
    return parts.join("; ");
  },
};
