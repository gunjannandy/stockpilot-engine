// C-078-1: news collect writes items; cards read ranked items.
import { describe, expect, it } from "vitest";
import { makeApp } from "../api/src/testkit";

const item = (id: string, source: string, weight: number) => ({
  id,
  link: `https://example.com/${id}`,
  title: `Title ${id}`,
  source,
  published_at: "2026-11-28T09:00:00+05:30",
  source_count: 1,
  weight,
});

describe("C-078-1 news items", () => {
  it("publishes ranked items and a card lists them in that order with their impacts", async () => {
    const t = await makeApp();
    const rows = [item("f", "NSE", 3), item("w", "Reuters", 2), item("b", "Blog", 1)];
    const stamp = {
      dataset: "news_items",
      source: "feeds",
      fetched_at: "2026-11-28T09:00:00+05:30",
      as_of: "2026-11-28",
      run_id: "n1",
    };
    expect((await t.signed("POST", "/api/publish/rows", { ...stamp, rows })).status).toBe(200);
    expect(
      (await t.signed("POST", "/api/publish/finish", { dataset: "news_items", run_id: "n1" }))
        .status,
    ).toBe(200);
    const r = (await (await t.app.request("/api/news")).json()) as {
      items: { id: string; impacts: unknown[] }[];
    };
    expect(r.items.map((i) => i.id)).toEqual(["f", "w", "b"]);
    expect(r.items.every((i) => Array.isArray(i.impacts))).toBe(true);
  });
});
