// C-158-2: on fixtures, every v2 D1 table, the KV queue and the vault's tables is copied, rebuilt or
// dropped per its list, and a rerun changes nothing.
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { discoverMaps } from "../tools/migrate/core/discover";
import { jsonDirSource, memorySink } from "../tools/migrate/core/io";
import { LIST } from "../tools/migrate/core/list";
import { migrate } from "../tools/migrate/core/run";
import type { AreaMap, Row } from "../tools/migrate/core/types";

const PORTFOLIO = {
  holdings: ["account", "source", "snapshot_at", "kind", "symbol", "isin"],
  trades: ["trade_key"],
  trade_tags: ["trade_key"],
  kite_syncs: ["account", "fetched_at"],
  corporate_actions: ["symbol", "ex_date", "kind"],
  action_terms: ["symbol", "ex_date", "kind"],
};

const fixtures: Record<string, Row[]> = {
  "vault:holdings": [
    {
      snapshot_at: "2026-11-26 15:40:00",
      kind: "stock",
      symbol: "AAA",
      isin: "X1",
      quantity: 10,
      avg_price: 100.5,
      source: "kite",
    },
    {
      snapshot_at: "2026-11-26 15:40:00",
      kind: "stock",
      symbol: "BBB",
      isin: "X2",
      quantity: 3,
      avg_price: 20,
      source: "kite",
    },
  ],
  "vault:trades": [
    {
      id: 1,
      trade_key: "T1",
      source: "tradebook",
      source_ref: "r1",
      kind: "stock",
      symbol: "AAA",
      isin: "X1",
      side: "buy",
      trade_date: "2026-01-02",
      quantity: 10,
      price: 100.5,
      currency: "INR",
      status: "confirmed",
    },
    {
      id: 2,
      trade_key: "T2",
      source: "tradebook",
      source_ref: "r1",
      kind: "stock",
      symbol: "AAA",
      isin: "X1",
      side: "sell",
      trade_date: "2026-02-02",
      quantity: 2,
      price: 120,
      currency: "INR",
      status: "confirmed",
    },
  ],
  "vault:trade_tags": [{ trade_key: "T1", placed_by: "owner", basket: null, how: "app" }],
  "vault:kite_syncs": [
    {
      fetched_at: "2026-11-26 15:41:00",
      trades: [{ a: 1 }],
      positions: { net: [] },
      margins: {},
      gtts: [],
    },
  ],
  "vault:corporate_actions": [
    {
      symbol: "AAA",
      isin: "X1",
      ex_date: "2026-03-01",
      kind: "split",
      numerator: 2,
      denominator: 1,
      subject: "split",
    },
  ],
  "vault:action_terms": [],
  "d1:feedback": [
    {
      id: "f1",
      person: "owner",
      text: "hello",
      status: "received",
      created_at: "2026-11-01T10:00:00+05:30",
    },
  ],
};

function writeSource(dir: string, withUnlisted = false): void {
  for (const e of LIST) {
    const k = `${e.kind}:${e.table}`;
    mkdirSync(join(dir, e.kind), { recursive: true });
    const rows = fixtures[k] ?? (e.action === "copy" ? [] : [{ x: 1 }, { x: 2 }]);
    // ndjson for the vault (streamed), json for the rest: both readers are exercised
    if (e.kind === "vault")
      writeFileSync(
        join(dir, e.kind, `${e.table}.ndjson`),
        rows.map((r) => JSON.stringify(r)).join("\n"),
      );
    else writeFileSync(join(dir, e.kind, `${e.table}.json`), JSON.stringify(rows));
  }
  if (withUnlisted) writeFileSync(join(dir, "vault", "surprise.json"), "[]");
}

// Stand-in for the maps other areas will add: a straight copy of every other `copy` table.
const others = (): AreaMap[] => {
  const tables: AreaMap["tables"] = {};
  for (const e of LIST)
    if (e.action === "copy" && e.area !== "portfolio")
      tables[`${e.kind}:${e.table}`] = {
        datasets: [`x_${e.kind}_${e.table}`],
        map: (row) => ({ dataset: `x_${e.kind}_${e.table}`, row }),
      };
  return [{ area: "others", tables }];
};
const sinkFor = () => {
  const ds: Record<string, string[]> = { ...PORTFOLIO };
  for (const m of others())
    for (const t of Object.values(m.tables))
      for (const d of t.datasets) ds[d] = ["id", "symbol", "x", "trade_key", "person"];
  return memorySink(ds);
};

describe("C-158-2 the per-table list", () => {
  it("covers every v2 D1 table, the KV queue and the vault, each once", () => {
    const d1 = LIST.filter((e) => e.kind === "d1")
      .map((e) => e.table)
      .sort();
    expect(d1).toEqual([
      "asks",
      "calls",
      "changes",
      "feedback",
      "job_lines",
      "jobs",
      "lists",
      "news_items",
      "news_rank",
      "news_tags",
      "quotes",
      "views",
      "write_budget",
    ]);
    expect(LIST.filter((e) => e.kind === "kv").map((e) => e.table)).toEqual(["queue"]);
    const keys = LIST.map((e) => `${e.kind}:${e.table}`);
    expect(new Set(keys).size).toBe(keys.length);
    expect(
      LIST.every((e) => e.reason.length > 5 && ["copy", "rebuild", "drop"].includes(e.action)),
    ).toBe(true);
  });

  it("copies, rebuilds or drops per the list, and a rerun changes nothing", async () => {
    const dir = mkdtempSync(join(tmpdir(), "mig-"));
    try {
      writeSource(dir);
      const maps = [...(await discoverMaps()), ...others()];
      const sink = sinkFor();
      const r1 = await migrate({ source: jsonDirSource(dir), sink, maps });
      expect(r1.problems).toEqual([]);
      expect(r1.ok).toBe(true);
      expect(r1.tables).toHaveLength(LIST.length);
      for (const t of r1.tables) {
        const entry = LIST.find((e) => e.kind === t.kind && e.table === t.table);
        expect(t.status).toBe(
          { copy: "copied", rebuild: "rebuild", drop: "dropped" }[entry?.action ?? "drop"],
        );
        if (t.status === "copied")
          for (const w of Object.values(t.v3)) expect(w.accepted).toBe(t.v2.rows);
      }
      expect(sink.rows("holdings")).toHaveLength(2);
      expect(sink.rows("trades")).toHaveLength(2);
      expect(sink.rows("trades")[0]?.account).toBe("main");
      expect(sink.rows("holdings")[0]?.snapshot_at).toBe("2026-11-26T15:40:00+05:30");
      expect(sink.rows("kite_syncs")[0]?.positions).toBe('{"net":[]}');
      const before = JSON.stringify(Object.keys(PORTFOLIO).map((d) => sink.rows(d)));
      const r2 = await migrate({ source: jsonDirSource(dir), sink, maps });
      expect(JSON.stringify(r2)).toBe(JSON.stringify(r1));
      expect(JSON.stringify(Object.keys(PORTFOLIO).map((d) => sink.rows(d)))).toBe(before);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("skips and reports a map whose target does not exist yet, and flags a table not on the list", async () => {
    const dir = mkdtempSync(join(tmpdir(), "mig-"));
    try {
      writeSource(dir, true);
      const r = await migrate({
        source: jsonDirSource(dir),
        sink: memorySink({}),
        maps: await discoverMaps(),
      });
      const trades = r.tables.find((t) => t.table === "trades" && t.kind === "vault");
      expect(trades?.status).toBe("skipped");
      expect(trades?.reason).toMatch(/no dataset trades/);
      expect(r.tables.find((t) => t.table === "calls" && t.kind === "d1")?.reason).toMatch(
        /no map yet/,
      );
      expect(r.problems.join()).toMatch(/surprise.*not on the list/);
      expect(r.ok).toBe(false);
      expect(JSON.stringify(r)).not.toMatch(/AAA|hello/); // the report holds no row content
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("reports held-back rows as a problem", async () => {
    const dir = mkdtempSync(join(tmpdir(), "mig-"));
    try {
      writeSource(dir);
      const sink = sinkFor();
      const tight = {
        ...sink,
        write: async (d: string, rows: Row[]) =>
          d === "trades" ? { accepted: 0, held_back: rows.length } : sink.write(d, rows),
      };
      const r = await migrate({
        source: jsonDirSource(dir),
        sink: tight,
        maps: [...(await discoverMaps()), ...others()],
      });
      expect(r.ok).toBe(false);
      expect(r.problems.join()).toMatch(/vault:trades -> trades: wrote 0 of 2, held back 2/);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
