// C-119-3: a browser holding the current run gets a 304 with no D1 read.
import { expect, it } from "vitest";
import { items, publishApp } from "../api/src/publish/testkit";

it("C-119-3 a browser holding the current run's ETag gets a 304 and D1 is not touched", async () => {
  const t = await publishApp();
  await t.rows("roomy", "a", items(3));
  await t.finish("roomy", "a");
  const first = await t.read("roomy");
  const etag = first.headers.get("etag");
  expect(etag).toBe('"roomy-a"');

  const before = t.sql.length;
  const second = await t.read("roomy", { "if-none-match": etag ?? "" });
  expect(second.status).toBe(304);
  expect(await second.text()).toBe("");
  expect(t.sql.length).toBe(before); // no D1 statement at all

  // After a new run publishes, the old ETag no longer matches and the browser gets the new answer.
  await t.rows("roomy", "b", items(2, 9));
  await t.finish("roomy", "b");
  const third = await t.read("roomy", { "if-none-match": etag ?? "" });
  expect(third.status).toBe(200);
  expect(third.headers.get("etag")).toBe('"roomy-b"');
});
