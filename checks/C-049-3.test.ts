// C-049-3: the lists Job reruns in market hours and each list carries its updated time.
import { describe, expect, it } from "vitest";
import { listsSlot } from "../api/src/lists/duty";
import { DUTIES, dutiesDue } from "../api/src/schedule/duties";
import { makeApp } from "../api/src/testkit";
import { datasets } from "../contract/src/index";

const reasons = JSON.stringify([{ key: "rank", en: "Ranked 1.", bn: "১ নম্বরে।" }]);
const at = "2026-11-28T10:00:00+05:30";
const row = (list: string, symbol: string, position: number) => ({
  id: `${list}:${symbol}`,
  list,
  symbol,
  exchange: "NSE",
  position,
  reasons_json: reasons,
  updated_at: at,
});

describe("C-049-3 the lists Job", () => {
  it("has its own duty every 30 minutes, and a slot per half hour", () => {
    const duty = DUTIES.find((d) => d.id === "lists");
    expect(duty?.everyMinutes).toBe(30);
    expect(datasets.lists.job).toBe("lists");
    expect(listsSlot(new Date("2026-11-28T04:44:00Z"))).toBe("1000"); // 10:14 IST
    expect(listsSlot(new Date("2026-11-28T04:46:00Z"))).toBe("1000");
    const slots = Array.from({ length: 12 }, (_, i) => new Date(Date.UTC(2026, 10, 28, 4, i * 5)));
    expect(slots.filter((s) => dutiesDue(s).some((d) => d.id === "lists")).length).toBe(2);
  });

  it("each list answers with its updated time and the screen's real counts", async () => {
    const t = await makeApp();
    const top = Array.from({ length: 10 }, (_, i) => row("top10", `S${i}`, i + 1));
    await t.signed("POST", "/api/publish/rows", {
      dataset: "lists",
      run_id: "l1",
      source: "test",
      fetched_at: at,
      as_of: at,
      rows: [...top, row("busy_today", "S3", 1)],
    });
    expect((await t.signed("POST", "/api/publish/finish", { dataset: "lists", run_id: "l1" })).status).toBe(200);
    const sha = "ab".repeat(32);
    await t.signed("POST", "/api/publish/finish", {
      dataset: "screen",
      run_id: "s1",
      source: "test",
      fetched_at: at,
      as_of: "2026-11-27",
      file: { name: `screen.${sha.slice(0, 12)}.json`, sha256: sha, rows: 2400 },
      summary: { analysed: 2400, passed: 700 },
    });
    const r = (await (await t.app.request("/api/lists")).json()) as {
      counts: { analysed: number; passed: number } | null;
      lists: { list: string; updated_at: string | null; rows: unknown[] }[];
    };
    expect(r.lists.map((l) => l.list)).toEqual(["top10", "just_missed", "has_view", "falling", "busy_today"]);
    expect(r.lists[0]?.updated_at).toBe(at);
    expect(r.lists[0]?.rows).toHaveLength(10);
    expect(r.lists[1]?.updated_at).toBeNull();
    expect(r.counts).toMatchObject({ analysed: 2400, passed: 700 });
  });

  it("holds back a row with no reason, and fails a run whose Top 10 is short", async () => {
    const t = await makeApp();
    const res = await t.signed("POST", "/api/publish/rows", {
      dataset: "lists",
      run_id: "l2",
      source: "test",
      fetched_at: at,
      as_of: at,
      rows: [{ ...row("top10", "A", 1), reasons_json: "[]" }, row("top10", "B", 2)],
    });
    expect(((await res.json()) as { held_back: number }).held_back).toBe(1);
    expect((await t.signed("POST", "/api/publish/finish", { dataset: "lists", run_id: "l2" })).status).toBe(422);
  });
});
