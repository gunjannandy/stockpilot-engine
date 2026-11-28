// C-052-1: a star writes one row and no Job row.
import { expect, it } from "vitest";
import { makeApp } from "../api/src/testkit";

const count = async (db: { prepare(q: string): { first(): Promise<unknown> } }, table: string) =>
  ((await db.prepare(`select count(*) as n from ${table}`).first()) as { n: number }).n;

it("C-052-1 a star is one watchlist row and no Job row; a stock and a fund both star", async () => {
  const t = await makeApp();
  await t.app.request("/api/ping"); // applies the migrations
  const jobs = await count(t.db, "job_runs");
  const post = (body: unknown) =>
    t.app.request("/api/watchlist", {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "content-type": "application/json" },
    });
  expect((await post({ id: "abc", kind: "stock" })).status).toBe(200);
  expect(await count(t.db, "watchlist")).toBe(1);
  expect(await count(t.db, "job_runs")).toBe(jobs);
  // a fund is starred by its ISIN, and starring twice is still one row
  expect((await post({ id: "INF000A00000", kind: "fund", name: "A fund" })).status).toBe(200);
  await post({ id: "ABC", kind: "stock" });
  expect(await count(t.db, "watchlist")).toBe(2);
  const list = (await (await t.app.request("/api/watchlist")).json()) as { items: { id: string; kind: string }[] };
  expect(list.items.map((i) => i.id).sort()).toEqual(["ABC", "INF000A00000"]);
  // un-star, then Undo is a second star
  await t.app.request("/api/watchlist/abc", { method: "DELETE" });
  expect(await count(t.db, "watchlist")).toBe(1);
  await post({ id: "ABC", kind: "stock" });
  expect(await count(t.db, "watchlist")).toBe(2);
  expect(await count(t.db, "job_runs")).toBe(jobs);
});
