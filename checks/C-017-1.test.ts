// C-017-1: a What's new note shows once per person and then never again. (API half; the browser half rides the preview e2e.)
import { expect, it } from "vitest";
import { makeApp } from "../api/src/testkit";

it("C-017-1 a note shows once and then never again", async () => {
  const { app, signed } = await makeApp();
  await signed("POST", "/api/whatsnew", { lines: [{ pr: 1, en: "Moved.", bn: "সরেছে।" }] });
  const get = async () =>
    ((await (await app.request("/api/whatsnew/unseen")).json()) as { lines: { pr: number }[] })
      .lines;
  expect((await get()).map((l) => l.pr)).toEqual([1]);
  await app.request("/api/whatsnew/seen", { method: "POST", body: JSON.stringify({ pr: 1 }) });
  expect(await get()).toEqual([]);
});
