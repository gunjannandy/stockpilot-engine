// C-114-1: a second identical Job is refused; one lock is held per kind; a failed step retries with backoff.
import { expect, it } from "vitest";
import { backoffMinutes, jobKey, withRetry } from "../api/src/jobs/runtime";
import { jobsApp } from "../api/src/jobs/testkit";

it("C-114-1 the key is kind, subject and day", () => {
  expect(jobKey("calendar", "all", "2026-11-27")).toBe("calendar|all|2026-11-27");
});

it("C-114-1 a second identical Job is refused, while it runs and after it is done", async () => {
  const t = await jobsApp();
  const first = await t.begin({ kind: "calendar", run_id: "r1" });
  expect(first.status).toBe(200);
  const again = await t.begin({ kind: "calendar", run_id: "r2" });
  expect(again.status).toBe(409);
  expect(((await again.json()) as { error: string }).error).toContain("duplicate");
  expect((await t.end("r1", "done")).status).toBe(200);
  expect((await t.begin({ kind: "calendar", run_id: "r3" })).status).toBe(409);
  expect(await t.count("job_runs")).toBe(1);
});

it("C-114-1 one lock is held per kind, and other kinds run beside it", async () => {
  const t = await jobsApp();
  expect((await t.begin({ kind: "news_collect", subject: "a", run_id: "n1" })).status).toBe(200);
  const second = await t.begin({ kind: "news_collect", subject: "b", run_id: "n2" });
  expect(second.status).toBe(423);
  expect(((await second.json()) as { error: string }).error).toContain("locked");
  expect((await t.begin({ kind: "ping", run_id: "p1" })).status).toBe(200);
  // Finishing the first frees the lock.
  await t.end("n1", "done");
  expect((await t.begin({ kind: "news_collect", subject: "b", run_id: "n2" })).status).toBe(200);
});

it("C-114-1 a lock nobody renewed for two hours is taken over", async () => {
  let now = new Date("2026-11-27T05:00:00Z");
  const t = await jobsApp({ now: () => now });
  await t.begin({ kind: "news_collect", subject: "a", run_id: "n1" });
  now = new Date("2026-11-27T07:30:00Z");
  expect((await t.begin({ kind: "news_collect", subject: "b", run_id: "n2" })).status).toBe(200);
});

it("C-114-1 a paused kind refuses to start", async () => {
  const t = await jobsApp();
  expect((await t.pause("calendar", true)).status).toBe(200);
  expect((await t.begin({ kind: "calendar", run_id: "r1" })).status).toBe(423);
  await t.pause("calendar", false);
  expect((await t.begin({ kind: "calendar", run_id: "r1" })).status).toBe(200);
});

it("C-114-1 a failed Job retries with doubling backoff, three times at most", async () => {
  expect([1, 2, 3, 4].map(backoffMinutes)).toEqual([2, 4, 8, 16]);
  expect(backoffMinutes(20)).toBe(60);
  let now = new Date("2026-11-27T05:00:00Z");
  const t = await jobsApp({ now: () => now });
  const retryAt: (string | null)[] = [];
  for (const id of ["r1", "r2", "r3"]) {
    expect((await t.begin({ kind: "calendar", run_id: id })).status).toBe(200);
    await t.end(id, "failed", "source down");
    retryAt.push((await t.run("calendar|all|2026-11-27")).retry_at);
    now = new Date(now.getTime() + 60 * 60_000);
  }
  expect(retryAt).toEqual(["2026-11-27T10:32:00+05:30", "2026-11-27T11:34:00+05:30", null]);
});

it("C-114-1 a failed step inside a Job retries with backoff and then gives up", async () => {
  const waits: number[] = [];
  let calls = 0;
  const out = await withRetry(
    async () => {
      calls++;
      if (calls < 3) throw new Error("flaky");
      return "ok";
    },
    { attempts: 4, baseMs: 1000, sleep: async (ms) => void waits.push(ms) },
  );
  expect(out).toBe("ok");
  expect(waits).toEqual([1000, 2000]);
  await expect(
    withRetry(
      async () => {
        throw new Error("always");
      },
      { attempts: 3, baseMs: 10, sleep: async () => {} },
    ),
  ).rejects.toThrow("always");
});
