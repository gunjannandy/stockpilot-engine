// Sources and sinks. A source is a folder of JSON the cockpit exports from v2 (D1, KV, the vault backup):
// `<dir>/<kind>/<table>.json` (an array) or `.ndjson` (one row a line, streamed so memory stays flat).
import { createHmac } from "node:crypto";
import { createReadStream, existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { createInterface } from "node:readline";
import type { Kind, Row, Sink, Source, Written } from "./types";

export function jsonDirSource(dir: string): Source {
  const file = (kind: Kind, table: string) =>
    [".ndjson", ".json"].map((x) => join(dir, kind, table + x)).find((f) => existsSync(f));
  return {
    has: (kind, table) => file(kind, table) !== undefined,
    tables: (kind) =>
      existsSync(join(dir, kind))
        ? readdirSync(join(dir, kind))
            .filter((f) => /\.(nd)?json$/.test(f))
            .map((f) => f.replace(/\.(nd)?json$/, ""))
        : [],
    async *rows(kind, table) {
      const f = file(kind, table);
      if (!f) return;
      if (f.endsWith(".json")) {
        for (const r of JSON.parse(readFileSync(f, "utf8")) as Row[]) yield r;
        return;
      }
      for await (const line of createInterface({
        input: createReadStream(f),
        crlfDelay: Number.POSITIVE_INFINITY,
      }))
        if (line.trim()) yield JSON.parse(line) as Row;
    },
  };
}

/** Test and Node twin: keeps rows by key (insert or replace), like the door does. */
export function memorySink(
  datasets: Record<string, string[]>,
): Sink & { rows(dataset: string): Row[]; writes: number } {
  const data = new Map<string, Map<string, Row>>();
  const self = {
    writes: 0,
    hasDataset: (d: string) => d in datasets,
    rows: (d: string) => [...(data.get(d)?.values() ?? [])],
    async write(dataset: string, rows: Row[]): Promise<Written> {
      const keys = datasets[dataset];
      if (!keys) return { accepted: 0, held_back: rows.length };
      const m = data.get(dataset) ?? new Map<string, Row>();
      data.set(dataset, m);
      for (const r of rows) m.set(JSON.stringify(keys.map((k) => r[k])), r);
      self.writes += rows.length;
      return { accepted: rows.length, held_back: 0 };
    },
  };
  return self;
}

/** Writes through the live ingest door: signed body, insert or replace, held to each dataset's day budget. */
export function ingestSink(opts: {
  baseUrl: string;
  hmacKey: string;
  datasets: Record<string, unknown>;
  fetch?: typeof fetch;
}): Sink {
  const f = opts.fetch ?? fetch;
  let n = 0;
  return {
    hasDataset: (d) => Object.hasOwn(opts.datasets, d),
    async write(dataset, rows) {
      const body = JSON.stringify({ dataset, run_id: `migrate-${dataset}-${++n}`, rows });
      const res = await f(`${opts.baseUrl}/api/ingest`, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-signature": createHmac("sha256", opts.hmacKey).update(body).digest("hex"),
        },
        body,
      });
      const j = (await res.json().catch(() => ({}))) as Partial<Written>;
      if (res.status === 429) return { accepted: 0, held_back: j.held_back ?? rows.length };
      if (!res.ok) throw new Error(`ingest ${dataset}: HTTP ${res.status}`);
      return { accepted: j.accepted ?? 0, held_back: j.held_back ?? 0 };
    },
  };
}
