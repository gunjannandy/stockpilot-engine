import { expect, it } from "vitest";
import { makeApp } from "../testkit";

it("What's new: posted lines show once per person, then never again", async () => {
  const { app, signed } = await makeApp();
  expect((await app.request("/api/whatsnew", { method: "POST", body: "{}" })).status).toBe(401);
  expect((await signed("POST", "/api/whatsnew", { lines: [{ pr: 7, en: "a" }] })).status).toBe(400);
  const lines = [{ pr: 7, en: "Search moved to the top.", bn: "সার্চ উপরে গেছে।" }];
  expect((await signed("POST", "/api/whatsnew", { lines })).status).toBe(200);
  expect((await signed("POST", "/api/whatsnew", { lines })).status).toBe(200); // idempotent
  const get = async () =>
    ((await (await app.request("/api/whatsnew/unseen")).json()) as { lines: unknown[] }).lines;
  expect(await get()).toEqual(lines);
  const seen = await app.request("/api/whatsnew/seen", {
    method: "POST",
    body: JSON.stringify({ pr: 7 }),
  });
  expect(seen.status).toBe(200);
  expect(await get()).toEqual([]);
});
