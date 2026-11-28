// Cron duties (decisions §2 Schedules): one Worker cron every 5 minutes puts one message per due duty on a
// Cloudflare Queue; the consumer runs each in its own invocation with its own heartbeat, so one failing or
// slow duty stops nothing else and each stays inside the 10 ms CPU limit.
import { datasets as registry } from "@stockpilot/contract";
import { githubFromEnv } from "../../../adapters/src/github";
import { istText } from "../app";
import type { Core } from "../jobs/runtime";
import { runSecretsDuty } from "../secrets/duty";
import { watcherDuty } from "../watcher/duties";
import { tick } from "./tick";

export type Duty = {
  id: string;
  /** Minutes between runs, a multiple of the cron's 5. */
  everyMinutes: number;
  /** Returns a short line for the log. A throw is recorded on the duty's heartbeat. */
  run(core: Core): Promise<string>;
};
export type DutyMessage = { duty: string };
export type Queue = { send(message: DutyMessage): Promise<void> };

const notYet = (what: string) => async () => `${what} is not built yet`;

/** The duties. Later tickets replace `run` for quotes, watcher and digest; add a duty by adding a line. */
export const DUTIES: Duty[] = [
  {
    id: "scheduler",
    everyMinutes: 5,
    async run(core) {
      const github = githubFromEnv(core.env as Record<string, string | undefined>);
      if (!github) return "no bot key set: nothing dispatched";
      const r = await tick(core, { github, datasets: registry });
      return `dispatched ${r.dispatched.length}, again ${r.redispatched.length}, retried ${r.retried.length}, refused ${r.failed.length}`;
    },
  },
  { id: "quotes", everyMinutes: 5, run: notYet("the quotes duty") },
  watcherDuty,
  { id: "secrets", everyMinutes: 60, run: (core) => runSecretsDuty(core) },
  { id: "digest", everyMinutes: 60, run: notYet("the digest") },
];

const CRON_MINUTES = 5;
/** Duties due at this cron firing: every duty whose interval divides the 5-minute slot counter. */
export const dutiesDue = (now: Date, duties: Duty[] = DUTIES) => {
  const slot = Math.floor(now.getTime() / (CRON_MINUTES * 60_000));
  return duties.filter((d) => slot % Math.max(1, Math.round(d.everyMinutes / CRON_MINUTES)) === 0);
};

/** The cron handler: one message per due duty. One that cannot be queued does not stop the others. */
export async function enqueueDuties(queue: Queue, now: Date, duties: Duty[] = DUTIES) {
  const failed: string[] = [];
  await Promise.all(
    dutiesDue(now, duties).map(async (d) => {
      try {
        await queue.send({ duty: d.id });
      } catch {
        failed.push(d.id);
      }
    }),
  );
  return { failed };
}

async function beat(core: Core, duty: Duty, ok: boolean, error: string | null) {
  const now = istText(core.now());
  const next = istText(new Date(core.now().getTime() + duty.everyMinutes * 2 * 60_000));
  await core.d1
    .prepare(
      `insert into heartbeats (part, version, at, ok, error, next_expected_by, last_success)
       values (?, ?, ?, ?, ?, ?, ?)
       on conflict(part) do update set version = excluded.version, at = excluded.at, ok = excluded.ok,
         error = excluded.error, next_expected_by = excluded.next_expected_by,
         last_success = case when excluded.ok = 1 then excluded.at else heartbeats.last_success end`,
    )
    .bind(`duty.${duty.id}`, core.version, now, ok ? 1 : 0, error, next, ok ? now : null)
    .run();
}

/** Run one duty in its own try: its heartbeat records the outcome and nothing propagates. */
export async function runDuty(core: Core, id: string, duties: Duty[] = DUTIES) {
  const duty = duties.find((d) => d.id === id);
  if (!duty) return { ok: false as const, detail: `no duty called ${id}` };
  try {
    const detail = await duty.run(core);
    await beat(core, duty, true, null);
    return { ok: true as const, detail };
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    try {
      await beat(core, duty, false, detail.slice(0, 300));
    } catch {
      // the beat itself failed: health shows the duty overdue, which is the right alarm
    }
    return { ok: false as const, detail };
  }
}

type Msg = { body: DutyMessage; ack(): void; retry(): void };
/** The queue consumer. Every message is acknowledged: a failure is on the heartbeat, and the next cron firing tries again. */
export async function handleBatch(batch: { messages: Msg[] }, core: Core, duties: Duty[] = DUTIES) {
  for (const m of batch.messages) {
    await runDuty(core, m.body.duty, duties);
    m.ack();
  }
}
