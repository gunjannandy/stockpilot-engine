// C-116-3: each cron duty runs as its own queue message and invocation with its own heartbeat; one throwing leaves the others run.
import { expect, it } from "vitest";
import { DUTIES, type Duty, enqueueDuties, handleBatch } from "../api/src/schedule/duties";
import { scheduleApp } from "../api/src/schedule/testkit";

const at = (iso: string) => new Date(iso);
const ids = (sent: { duty: string }[]) => sent.map((m) => m.duty).sort();

it("C-116-3 the cron puts one message per due duty on the queue", async () => {
  const sent: { duty: string }[] = [];
  const queue = { send: async (m: { duty: string }) => void sent.push(m) };
  await enqueueDuties(queue, at("2026-11-27T04:00:00Z"));
  expect(ids(sent)).toEqual(["digest", "quotes", "scheduler", "secrets", "watcher"]);
  sent.length = 0;
  await enqueueDuties(queue, at("2026-11-27T04:05:00Z"));
  expect(ids(sent)).toEqual(["quotes", "scheduler"]);
  sent.length = 0;
  await enqueueDuties(queue, at("2026-11-27T04:15:00Z"));
  expect(ids(sent)).toEqual(["quotes", "scheduler", "watcher"]);
  expect(DUTIES.map((d) => d.id).sort()).toEqual([
    "digest",
    "quotes",
    "scheduler",
    "secrets",
    "watcher",
  ]);
});

it("C-116-3 a duty that cannot be queued does not stop the others being queued", async () => {
  const sent: string[] = [];
  const queue = {
    send: async (m: { duty: string }) => {
      if (m.duty === "scheduler") throw new Error("queue full");
      sent.push(m.duty);
    },
  };
  await enqueueDuties(queue, at("2026-11-27T04:00:00Z"));
  expect(sent.sort()).toEqual(["digest", "quotes", "secrets", "watcher"]);
});

it("C-116-3 each message runs its own duty with its own heartbeat, and one throwing leaves the others run", async () => {
  const t = await scheduleApp();
  const ran: string[] = [];
  const duties: Duty[] = [
    {
      id: "scheduler",
      everyMinutes: 5,
      run: async () => {
        throw new Error("boom");
      },
    },
    {
      id: "quotes",
      everyMinutes: 5,
      run: async () => {
        ran.push("quotes");
        return "12 quotes";
      },
    },
    {
      id: "watcher",
      everyMinutes: 15,
      run: async () => {
        ran.push("watcher");
        return "all green";
      },
    },
  ];
  const acked: string[] = [];
  const msg = (duty: string) => ({
    body: { duty },
    ack: () => void acked.push(duty),
    retry: () => void acked.push(`retry-${duty}`),
  });
  await handleBatch(
    { messages: [msg("scheduler"), msg("quotes"), msg("watcher")] },
    t.core(at("2026-11-27T04:00:00Z")),
    duties,
  );
  expect(ran).toEqual(["quotes", "watcher"]);
  expect(acked.sort()).toEqual(["quotes", "scheduler", "watcher"]);
  const beats = (await t.db.prepare("select * from heartbeats order by part").all()).results as {
    part: string;
    ok: number;
    error: string | null;
    next_expected_by: string | null;
    last_success: string | null;
  }[];
  expect(beats.map((b) => [b.part, b.ok])).toEqual([
    ["duty.quotes", 1],
    ["duty.scheduler", 0],
    ["duty.watcher", 1],
  ]);
  expect(beats[1]?.error).toContain("boom");
  // Expected again within two of its own intervals.
  expect(beats[0]?.next_expected_by).toBe("2026-11-27T09:40:00+05:30");
  expect(beats[2]?.next_expected_by).toBe("2026-11-27T10:00:00+05:30");
});

it("C-116-3 a failing duty keeps the last success it had", async () => {
  const t = await scheduleApp();
  let fail = false;
  const duties: Duty[] = [
    {
      id: "quotes",
      everyMinutes: 5,
      run: async () => {
        if (fail) throw new Error("later");
        return "ok";
      },
    },
  ];
  const m = { body: { duty: "quotes" }, ack() {}, retry() {} };
  await handleBatch({ messages: [m] }, t.core(at("2026-11-27T04:00:00Z")), duties);
  fail = true;
  await handleBatch({ messages: [m] }, t.core(at("2026-11-27T04:05:00Z")), duties);
  const b = (await t.db.prepare("select * from heartbeats where part = 'duty.quotes'").first()) as {
    ok: number;
    last_success: string;
  };
  expect(b.ok).toBe(0);
  expect(b.last_success).toBe("2026-11-27T09:30:00+05:30");
});

it("C-116-3 an unknown duty is acknowledged and recorded as failed, not retried forever", async () => {
  const t = await scheduleApp();
  const acked: string[] = [];
  await handleBatch(
    {
      messages: [
        {
          body: { duty: "nope" },
          ack: () => void acked.push("ack"),
          retry: () => void acked.push("retry"),
        },
      ],
    },
    t.core(at("2026-11-27T04:00:00Z")),
    [],
  );
  expect(acked).toEqual(["ack"]);
});
