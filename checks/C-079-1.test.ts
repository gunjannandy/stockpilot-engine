// C-079-1: impact rows are append-only and complete.
import { readdirSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { makeApp } from "../api/src/testkit";

const row = (over: Record<string, unknown> = {}) => ({
  id: "a:ABC",
  item_id: "a",
  symbol: "ABC",
  exchange: "NSE",
  relation: "self",
  direction: "good",
  size: "large",
  sector_only: false,
  why_en: "Profit up.",
  why_bn: "লাভ বেড়েছে।",
  weight: 3,
  judged_at: "2026-11-28T09:15:00+05:30",
  ...over,
});

describe("C-079-1 impact table", () => {
  it("a second write of the same item and stock changes nothing, and no code updates or deletes a row", async () => {
    const t = await makeApp();
    const first = (await (
      await t.signed("POST", "/api/news/impact", { rows: [row()], judged_ids: ["a"] })
    ).json()) as { written: number };
    expect(first.written).toBe(1);
    const again = (await (
      await t.signed("POST", "/api/news/impact", { rows: [row({ direction: "bad" })] })
    ).json()) as { written: number; ignored: number };
    expect([again.written, again.ignored]).toEqual([0, 1]);
    const stored = (await t.db
      .prepare("select direction from news_impact where id = 'a:ABC'")
      .first()) as { direction: string };
    expect(stored.direction).toBe("good");
    // No code path updates or deletes an impact row: scan every source in the area (and the email reader).
    for (const dir of ["news", "email", "og", "digest"])
      for (const f of readdirSync(new URL(`../api/src/${dir}/`, import.meta.url)).filter((n) =>
        n.endsWith(".ts"),
      ))
        expect(
          readFileSync(new URL(`../api/src/${dir}/${f}`, import.meta.url), "utf8"),
          f,
        ).not.toMatch(/(update|delete\s+from)\s+news_impact/i);
  });

  it("holds back an incomplete row: a sector-only link with a direction, or a why with no Bengali", async () => {
    const t = await makeApp();
    const res = (await (
      await t.signed("POST", "/api/news/impact", {
        rows: [
          row({
            id: "b:XYZ",
            item_id: "b",
            symbol: "XYZ",
            relation: "sector",
            sector_only: true,
            direction: "bad",
          }),
          row({ id: "c:ABC", item_id: "c", why_bn: "" }),
        ],
      })
    ).json()) as { written: number; held: unknown[] };
    expect([res.written, res.held.length]).toEqual([0, 2]);
  });

  it("refuses an unsigned write and lists judged items for the Job", async () => {
    const t = await makeApp();
    expect((await t.app.request("/api/news/impact", { method: "POST", body: "{}" })).status).toBe(
      401,
    );
    await t.signed("POST", "/api/news/impact", { rows: [], judged_ids: ["z"] });
    const j = (await (await t.signed("GET", "/api/news/judged")).json()) as { item_ids: string[] };
    expect(j.item_ids).toEqual(["z"]);
  });
});
