// C-122-1: a forced red opens exactly one issue, and only one however often the watcher runs.
import { expect, it } from "vitest";
import { opsApp } from "../api/src/watcher/testkit";
import { watch } from "../api/src/watcher/watcher";

it("C-122-1 a forced red opens exactly one issue; green closes the episode", async () => {
  const t = await opsApp();
  await t.heartbeat("job.ping", false, "boom");
  await watch(t.core(), t.github);
  await watch(t.core(), t.github);
  await Promise.all([watch(t.core(), t.github), watch(t.core(), t.github)]);
  const mine = t.github.issues.filter((i) => i.title.includes("job.ping"));
  expect(mine).toHaveLength(1);
  expect(t.github.issues).toHaveLength(1);
  // back to green, then red again: a new episode, a second issue
  await t.heartbeat("job.ping", true, null);
  await watch(t.core(), t.github);
  await t.heartbeat("job.ping", false, "again");
  await watch(t.core(), t.github);
  expect(t.github.issues).toHaveLength(2);
});

it("C-122-1 a browser-error spike opens one issue", async () => {
  const t = await opsApp();
  for (let i = 0; i < 12; i++) await t.browserError(i);
  await watch(t.core(), t.github);
  await watch(t.core(), t.github);
  expect(t.github.issues.filter((i) => i.title.includes("browser errors"))).toHaveLength(1);
});
