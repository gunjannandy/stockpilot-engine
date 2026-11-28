// LO206: health lists the duty and calendar parts, and an empty calendar turns job.calendar amber.
import { expect, it } from "vitest";
import { makeApp } from "../api/src/testkit";
import { PARTS } from "../contract/src";

it("LO206 health carries the new parts and folds the calendar check in", async () => {
  const { withSecret } = await makeApp({ now: () => new Date("2026-11-27T03:30:00Z") });
  const h = (await (await withSecret("/api/health")).json()) as {
    parts: { part: string; status: string; error: string | null }[];
  };
  for (const p of ["duty.scheduler", "duty.quotes", "duty.watcher", "duty.digest", "job.calendar"])
    expect(PARTS).toContain(p);
  const cal = h.parts.find((p) => p.part === "job.calendar");
  expect(cal?.status).toBe("amber");
  expect(cal?.error).toContain("market calendar");
});
