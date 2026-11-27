// C-119-1: a pane answer is served from the edge cache until its dataset's pointer moves.
import { expect, it } from "vitest";
import { items, publishApp } from "../api/src/publish/testkit";

const rowReads = (sql: string[]) => sql.filter((s) => /from dataset_rows/.test(s)).length;

it("C-119-1 the answer is built once per run and rebuilt only when the pointer moves", async () => {
  const t = await publishApp();
  await t.rows("roomy", "a", items(3));
  await t.finish("roomy", "a");
  await t.read("roomy"); // warms boot and builds the answer
  const before = rowReads(t.sql);
  const again = await t.read("roomy");
  expect(((await again.json()) as { rows: unknown[] }).rows).toHaveLength(3);
  await t.read("roomy");
  expect(rowReads(t.sql)).toBe(before); // served from the cache: no dataset row read

  await t.rows("roomy", "b", items(4, 50));
  await t.finish("roomy", "b");
  const moved = (await (await t.read("roomy")).json()) as { run_id: string; rows: unknown[] };
  expect(moved.run_id).toBe("b");
  expect(moved.rows).toHaveLength(4);
  expect(rowReads(t.sql)).toBeGreaterThan(before);
});
