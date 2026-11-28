// C-046-1: the quotes route answers from the cache within its age limit, and says how old the price is.
import { expect, it } from "vitest";
import { writeQuotes } from "../api/src/quotes/quotes";
import { makeApp } from "../api/src/testkit";

it("C-046-1 a fresh quote is served with its age; an old one is listed as stale", async () => {
  let now = new Date("2026-11-30T05:00:00Z");
  const { app, db } = await makeApp({ now: () => now });
  await app.request("/api/ping"); // boot: migrations
  await writeQuotes({ d1: db, now: () => now }, [{ symbol: "ABC", price: 101.5, prev_close: 100 }]);
  now = new Date(now.getTime() + 120_000);
  const fresh = await (await app.request("/api/quotes?symbols=abc,XYZ")).json();
  expect(fresh.quotes).toHaveLength(1);
  expect(fresh.quotes[0]).toMatchObject({ symbol: "ABC", price: 101.5, age_seconds: 120 });
  expect(fresh.stale).toEqual(["XYZ"]);
  now = new Date(now.getTime() + fresh.max_age_seconds * 1000);
  const old = await (await app.request("/api/quotes?symbols=ABC")).json();
  expect(old.quotes).toEqual([]);
  expect(old.stale).toEqual(["ABC"]);
});
