// R2: every `copy` row of the per-table list has a map; the maps' rows fit the v3 tables, calls keep their v2 date,
// and a rerun changes nothing. Fixtures are invented and shaped like v2's rows.
import { describe, expect, it } from "vitest";
import { CallRow } from "../contract/src/calls/calls";
import { datasets } from "../contract/src/datasets";
import { migrationDatasets } from "../contract/src/migrate/migrate";
import { discoverMaps } from "../tools/migrate/core/discover";
import { memorySink } from "../tools/migrate/core/io";
import { keyOf, LIST } from "../tools/migrate/core/list";
import { migrate } from "../tools/migrate/core/run";
import type { Row, Source } from "../tools/migrate/core/types";

const call = {
  symbol: "FIXA",
  exchange: "NSE",
  call: "buy",
  chance_3m: 0.62,
  chance_6m: null,
  low_3m: 95,
  high_3m: 121,
  model: "m1",
  form: JSON.stringify({
    reasons_for: [{ text: "Profit is growing" }],
    bengali: { summary: "ভালো" },
  }),
  as_of: "2026-11-26",
  written_at: "2026-11-26 09:15:00",
};
const fixtures: Record<string, Row[]> = {
  "d1:calls": [call, { ...call, symbol: "FIXB", call: "wait", chance_3m: null }],
  "vault:calls": [{ ...call, as_of: "2026-10-01" }, call],
  "d1:lists": [
    {
      list_name: "worth_following",
      symbol: "FIXA",
      exchange: "NSE",
      rank: 1,
      reason: "r",
      reason_bn: null,
      since: "2026-11-26 09:00:00",
    },
    {
      list_name: "holdings",
      symbol: "FIXA",
      exchange: "NSE",
      rank: 1,
      reason: "r",
      reason_bn: null,
      since: "2026-11-26 09:00:00",
    },
  ],
  "vault:watchlist": [
    { symbol: "FIXA", added_at: "2026-11-01 10:00:00", removed_at: null },
    { symbol: "FIXB", added_at: "2026-11-01 10:00:00", removed_at: "2026-11-02 10:00:00" },
  ],
  "vault:not_now": [
    { symbol: "FIXB", until: "2026-12-01 00:00:00", created_at: "2026-11-24 10:00:00" },
  ],
  "vault:archived_days": [{ day: "2026-11-25", page: "{}" }],
  "vault:long_term_marks": [{ symbol: "FIXA", marked_at: "2026-11-02 10:00:00" }],
  "vault:smallcase_orders": [{ id: 7, placed_at: "2026-11-03 10:00:00", status: "done" }],
  "vault:fund_calls": [
    { id: "F1", name: "Fixture Fund", call: "buy", rank: 3, of: 40, as_of: "2026-11-26" },
  ],
  "vault:target_allocations": [{ allocation: { stocks: 0.6, gold: 0.4 } }],
  "vault:budgets": [{ month: "2026-11", amount_inr: 100 }],
};
const source = (): Source => ({
  has: (k, t) => keyOf(k, t) in fixtures,
  tables: (k) =>
    Object.keys(fixtures)
      .filter((x) => x.startsWith(`${k}:`))
      .map((x) => x.slice(k.length + 1)),
  async *rows(k, t) {
    for (const r of fixtures[keyOf(k, t)] ?? []) yield r;
  },
});
const ds = () =>
  Object.fromEntries(Object.entries(migrationDatasets).map(([k, v]) => [k, [...v.keys]]));

describe("R2 v2 copy maps", () => {
  it("has a map for every copy row on the list", async () => {
    const maps = new Set((await discoverMaps()).flatMap((m) => Object.keys(m.tables)));
    for (const e of LIST)
      if (e.action === "copy") expect(maps.has(keyOf(e.kind, e.table))).toBe(true);
  });

  it("makes calls that keep their v2 date and pass the v3 schema", async () => {
    const maps = await discoverMaps();
    const m = maps.find((x) => x.area === "calls")?.tables["d1:calls"];
    const out = m?.map(call) as { row: Row }[];
    expect(out).toHaveLength(1);
    const row = out[0]?.row as Row;
    expect(row.made_on).toBe("2026-11-26");
    expect(row.id).toBe("NSE:FIXA:2026-11-26:63");
    expect(row.verdict).toBe("Buy");
    expect(CallRow.safeParse({ ...row, limited: false }).success).toBe(true);
    expect(migrationDatasets.calls.row.safeParse(row).success).toBe(true);
    const none = m?.map({ ...call, call: "wait", chance_3m: null }) as { row: Row }[];
    expect(none[0]?.row.verdict).toBe("No view yet");
    expect(none[0]?.row.chance).toBeNull();
  });

  it("copies the fixtures, every row fits its table, and a rerun changes nothing", async () => {
    const sink = memorySink({ ...ds(), fund_calls: ["id"], feedback: ["id"] });
    const strict = {
      ...sink,
      write: async (d: string, rows: Row[]) => {
        const schema =
          (
            migrationDatasets as Record<
              string,
              { row: { safeParse(v: unknown): { success: boolean } } }
            >
          )[d]?.row ??
          (datasets as Record<string, { row: { safeParse(v: unknown): { success: boolean } } }>)[d]
            ?.row;
        const good = rows.filter((r) => schema?.safeParse(r).success);
        await sink.write(d, good);
        return { accepted: good.length, held_back: rows.length - good.length };
      },
    };
    const run = () => migrate({ source: source(), sink: strict, maps: await_maps });
    const await_maps = await discoverMaps();
    const r1 = await run();
    const mine = r1.problems.filter(
      (p) =>
        /calls|lists|record|fund_calls|watchlist|not_now|archived|marks|smallcase|budgets|allocations/.test(
          p,
        ) && !/no map yet|no dataset/.test(p),
    );
    expect(mine).toEqual([]);
    expect(sink.rows("calls")).toHaveLength(3);
    expect(sink.rows("watchlist")).toHaveLength(1);
    expect(sink.rows("list_rows")).toHaveLength(1);
    expect(sink.rows("fund_calls")).toHaveLength(1);
    const before = JSON.stringify(Object.keys(ds()).map((d) => sink.rows(d)));
    const r2 = await run();
    expect(JSON.stringify(r2)).toBe(JSON.stringify(r1));
    expect(JSON.stringify(Object.keys(ds()).map((d) => sink.rows(d)))).toBe(before);
  });
});
