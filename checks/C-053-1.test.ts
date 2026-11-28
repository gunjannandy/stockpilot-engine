// C-053-1: Not now rows expire after a week or a month and Undo removes them.
import { expect, it } from "vitest";
import { makeApp } from "../api/src/testkit";

it("C-053-1 Not now lasts a week or a month, ends by itself, and Undo removes it", async () => {
  let now = new Date("2026-11-28T06:00:00Z");
  const t = await makeApp({ now: () => now });
  const post = (symbol: string, f: string) =>
    t.app.request("/api/not-now", {
      method: "POST",
      body: JSON.stringify({ symbol, for: f }),
      headers: { "content-type": "application/json" },
    });
  const hidden = async () =>
    ((await (await t.app.request("/api/watchlist")).json()) as { not_now: { symbol: string }[] }).not_now
      .map((n) => n.symbol)
      .sort();
  const w = (await (await post("abc", "week")).json()) as { until: string };
  await post("xyz", "month");
  expect(w.until).toBe("2026-12-05T11:30:00+05:30");
  expect(await hidden()).toEqual(["ABC", "XYZ"]);
  now = new Date("2026-12-06T06:00:00Z"); // a week and a day later
  expect(await hidden()).toEqual(["XYZ"]);
  now = new Date("2026-12-29T06:00:00Z"); // past a month
  expect(await hidden()).toEqual([]);
  // Undo removes a live row at once
  now = new Date("2026-11-28T06:00:00Z");
  await post("abc", "month");
  await t.app.request("/api/not-now/abc", { method: "DELETE" });
  expect(await hidden()).toEqual(["XYZ"]);
  expect((await post("abc", "year")).status).toBe(400);
});
