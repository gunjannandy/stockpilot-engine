// C-136-1: a forced red inside a version's first hour rolls production back, opens a hotfix issue and pauses releases; once.

import { expect, it } from "vitest";
import { fakePlatform } from "../adapters/src/cloudflare";
import { opsApp } from "../api/src/watcher/testkit";
import { smoke } from "../api/src/watcher/watcher";
import { PAUSE_RELEASES } from "../contract/src";

it("C-136-1 red within the hour rolls back, opens a hotfix issue and pauses releases, once", async () => {
  const t = await opsApp();
  const platform = fakePlatform();
  await t.heartbeat("job.ping", false, "boom");
  const r = await smoke(t.core(), { github: t.github, platform });
  expect(r.rolledBack).toBe(true);
  expect(platform.rollbacks).toHaveLength(1);
  expect(t.github.issues.filter((i) => i.labels.includes("hotfix"))).toHaveLength(1);
  expect(await t.flag(PAUSE_RELEASES)).toBe(true);
  await smoke(t.core(), { github: t.github, platform });
  expect(platform.rollbacks).toHaveLength(1);
  expect(t.github.issues).toHaveLength(1);
});

it("C-136-1 green, or red after the first hour, rolls nothing back", async () => {
  const t = await opsApp();
  const platform = fakePlatform();
  expect((await smoke(t.core(), { github: t.github, platform })).rolledBack).toBe(false);
  await t.heartbeat("job.ping", false, "boom");
  const late = new Date(t.now.getTime() + 61 * 60_000);
  expect((await smoke(t.core(late), { github: t.github, platform })).rolledBack).toBe(false);
  expect(platform.rollbacks).toHaveLength(0);
  expect(await t.flag(PAUSE_RELEASES)).toBe(false);
});

it("C-136-1 a failed rollback still opens the hotfix issue and pauses releases", async () => {
  const t = await opsApp();
  await t.heartbeat("job.ping", false, "boom");
  const r = await smoke(t.core(), { github: t.github, platform: fakePlatform({ fail: true }) });
  expect(r.rolledBack).toBe(false);
  expect(t.github.issues[0]?.body).toContain("FAILED");
  expect(await t.flag(PAUSE_RELEASES)).toBe(true);
});
