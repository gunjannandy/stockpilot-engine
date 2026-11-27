// C-021-1: a run that fails its checks leaves the last good run served with its date.
import { expect, it } from "vitest";
import { items, publishApp } from "../api/src/publish/testkit";

it("C-021-1 a failed run leaves the last good run served, with its date", async () => {
  const t = await publishApp();
  expect((await t.rows("small", "a", items(3), "2026-11-26")).status).toBe(200);
  expect((await t.finish("small", "a")).status).toBe(200);

  // Run b fails its run check (one row only).
  await t.rows("small", "b", items(1, 10), "2026-11-27");
  const bad = await t.finish("small", "b");
  expect(bad.status).toBe(422);
  const verdict = (await bad.json()) as {
    published: boolean;
    reason: string;
    serving: { run_id: string; as_of: string };
  };
  expect(verdict.published).toBe(false);
  expect(verdict.reason).toMatch(/fewer than two rows/);
  expect(verdict.serving).toEqual({ run_id: "a", as_of: "2026-11-26" });

  const seen = (await (await t.read("small")).json()) as {
    run_id: string;
    as_of: string;
    rows: { id: string }[];
  };
  expect(seen.run_id).toBe("a");
  expect(seen.as_of).toBe("2026-11-26");
  expect(seen.rows.map((r) => r.id)).toEqual(["r0", "r1", "r2"]);
});
