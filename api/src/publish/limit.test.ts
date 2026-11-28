import { expect, test } from "vitest";
import { items, publishApp } from "./testkit";

test("a dataset that states a larger rowsLimit takes more than 1,000 rows in a run", async () => {
  const t = await publishApp();
  expect((await t.rows("wide", "w1", items(1000))).status).toBe(200);
  expect((await t.rows("wide", "w1", items(400, 1000))).status).toBe(200);
  const done = await t.finish("wide", "w1");
  expect(done.status).toBe(200);
  expect(((await done.json()) as { published: boolean }).published).toBe(true);
});

test("a dataset without a rowsLimit still stops at 1,000 rows", async () => {
  const t = await publishApp();
  expect((await t.rows("roomy", "r1", items(1000))).status).toBe(200);
  expect((await t.rows("roomy", "r1", items(1, 1000))).status).toBe(413);
  expect((await t.rows("wide", "w2", items(1501))).status).toBe(413);
});
