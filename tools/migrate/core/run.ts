import { Fingerprint } from "./checksum";
import { keyOf, LIST } from "./list";
import type { AreaMap, Entry, Row, Sink, Source, TableMap } from "./types";

export type TableReport = {
  kind: string;
  table: string;
  action: Entry["action"];
  area: string;
  status: "copied" | "rebuild" | "dropped" | "skipped" | "problem";
  reason: string;
  v2: { rows: number; sha: string };
  v3: Record<string, { rows: number; sha: string; accepted: number; held_back: number }>;
};
/** Counts and checksums only: never row content. */
export type Report = { ok: boolean; problems: string[]; tables: TableReport[] };

const BATCH = 1000;

async function copyTable(
  entry: Entry,
  map: TableMap,
  source: Source,
  sink: Sink,
): Promise<{ v2: Fingerprint; v3: TableReport["v3"] }> {
  const v2 = new Fingerprint();
  const out = new Map<string, Fingerprint>();
  const acc = new Map<string, { accepted: number; held_back: number }>();
  const buf = new Map<string, Row[]>();
  const flush = async (ds: string) => {
    const rows = buf.get(ds);
    if (!rows?.length) return;
    buf.set(ds, []);
    const w = await sink.write(ds, rows);
    const a = acc.get(ds) ?? { accepted: 0, held_back: 0 };
    acc.set(ds, { accepted: a.accepted + w.accepted, held_back: a.held_back + w.held_back });
  };
  for (const ds of map.datasets) {
    out.set(ds, new Fingerprint());
    acc.set(ds, { accepted: 0, held_back: 0 });
    buf.set(ds, []);
  }
  for await (const row of source.rows(entry.kind, entry.table)) {
    v2.add(row);
    const made = map.map(row);
    for (const m of made === null ? [] : Array.isArray(made) ? made : [made]) {
      out.get(m.dataset)?.add(m.row);
      const b = buf.get(m.dataset);
      if (!b)
        throw new Error(
          `${keyOf(entry.kind, entry.table)} wrote to ${m.dataset}, which it did not declare`,
        );
      b.push(m.row);
      if (b.length >= BATCH) await flush(m.dataset);
    }
  }
  for (const ds of map.datasets) await flush(ds);
  const v3: TableReport["v3"] = {};
  for (const [ds, fp] of out)
    v3[ds] = {
      rows: fp.count,
      sha: fp.sha,
      ...(acc.get(ds) as { accepted: number; held_back: number }),
    };
  return { v2, v3 };
}

/** Runs the list against a source and a sink. Idempotent: the sink replaces by key, the report holds no times. */
export async function migrate(opts: {
  source: Source;
  sink: Sink;
  maps: AreaMap[];
  list?: Entry[];
}): Promise<Report> {
  const list = opts.list ?? LIST;
  const maps = new Map<string, TableMap>();
  for (const m of opts.maps) for (const [k, t] of Object.entries(m.tables)) maps.set(k, t);
  const tables: TableReport[] = [];
  const problems: string[] = [];

  for (const entry of list) {
    const key = keyOf(entry.kind, entry.table);
    const base = {
      kind: entry.kind,
      table: entry.table,
      action: entry.action,
      area: entry.area,
      reason: entry.reason,
    };
    const present = opts.source.has(entry.kind, entry.table);
    const none = { rows: 0, sha: new Fingerprint().sha };
    if (!present) {
      tables.push({
        ...base,
        status: entry.action === "copy" ? "problem" : "dropped",
        v2: none,
        v3: {},
        reason: `${entry.reason} (not in the backup)`,
      });
      if (entry.action === "copy") problems.push(`${key}: not in the backup`);
      continue;
    }
    if (entry.action !== "copy") {
      const fp = new Fingerprint();
      for await (const r of opts.source.rows(entry.kind, entry.table)) fp.add(r);
      tables.push({
        ...base,
        status: entry.action === "drop" ? "dropped" : "rebuild",
        v2: { rows: fp.count, sha: fp.sha },
        v3: {},
      });
      continue;
    }
    const map = maps.get(key);
    if (!map) {
      tables.push({
        ...base,
        status: "skipped",
        reason: `no map yet from area "${entry.area}"`,
        v2: none,
        v3: {},
      });
      problems.push(`${key}: no map yet from area "${entry.area}"`);
      continue;
    }
    const missing = map.datasets.filter((d) => !opts.sink.hasDataset(d));
    if (missing.length) {
      tables.push({
        ...base,
        status: "skipped",
        reason: `v3 has no dataset ${missing.join(", ")} yet`,
        v2: none,
        v3: {},
      });
      problems.push(`${key}: v3 has no dataset ${missing.join(", ")}`);
      continue;
    }
    const { v2, v3 } = await copyTable(entry, map, opts.source, opts.sink);
    const bad = Object.entries(v3).filter(([, w]) => w.accepted !== w.rows || w.held_back > 0);
    for (const [ds, w] of bad)
      problems.push(`${key} -> ${ds}: wrote ${w.accepted} of ${w.rows}, held back ${w.held_back}`);
    tables.push({
      ...base,
      status: bad.length ? "problem" : "copied",
      v2: { rows: v2.count, sha: v2.sha },
      v3,
    });
  }

  const known = new Set(list.map((e) => keyOf(e.kind, e.table)));
  for (const kind of ["d1", "kv", "vault"] as const)
    for (const t of opts.source.tables(kind))
      if (!known.has(keyOf(kind, t)))
        problems.push(`${keyOf(kind, t)}: in the backup but not on the list`);

  return { ok: problems.length === 0, problems, tables };
}
