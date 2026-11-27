// Preview data (decisions §5): public datasets come from production's public files, a dataset with no
// file yet gets made-up rows, and private tables only ever hold made-up rows. Running it again is the
// nightly reseed: every dataset's table is emptied first, so whatever a preview collected is gone.
import type { Dataset } from "@stockpilot/contract";
import { z } from "zod";
import { fakeRows } from "../../../tools/fake/generate";
import { istDay } from "../app";

/** Production's rows for a public dataset, or null when it has no file (yet). */
export type PublicSource = (dataset: string) => Promise<unknown[] | null>;
export type Seeded = { dataset: string; from: "production" | "made-up"; rows: number };

export const MADE_UP_ROWS = 20;

export const publicFileUrl = (base: string, dataset: string) =>
  `${base.replace(/\/+$/, "")}/data/${dataset}.json`;

/** Reads `<base>/data/<dataset>.json` ({ rows } or a bare array); any miss or error is "no file". */
export function publicSourceFrom(
  base: string,
  fetcher: (url: string) => Promise<Response> = (u) => fetch(u),
): PublicSource {
  return async (dataset) => {
    try {
      const res = await fetcher(publicFileUrl(base, dataset));
      if (!res.ok) return null;
      const body = (await res.json()) as unknown;
      const rows = Array.isArray(body) ? body : (body as { rows?: unknown }).rows;
      return Array.isArray(rows) ? rows : null;
    } catch {
      return null;
    }
  };
}

type Registry = Record<string, Dataset>;
const IDENT = /^[a-z][a-z0-9_]*$/;
type D1 = {
  prepare(sql: string): { bind(...v: unknown[]): unknown };
  batch(s: never[]): Promise<unknown>;
};

export async function seedPreview(
  d1: D1,
  opts: { datasets: Registry; publicSource: PublicSource; seed?: number; now?: () => Date },
): Promise<Seeded[]> {
  // The seed is the IST day unless given, so the nightly run changes the made-up rows each night.
  const day = Number(istDay((opts.now ?? (() => new Date()))()).replaceAll("-", ""));
  const seed = opts.seed ?? day;
  const out: Seeded[] = [];
  for (const ds of Object.values(opts.datasets).sort((a, b) => a.name.localeCompare(b.name))) {
    if (!IDENT.test(ds.table) || !(ds.row instanceof z.ZodObject)) continue;
    const schema = ds.row as z.ZodObject;
    // Private datasets never ask production for anything.
    const fromProd =
      (ds.visibility ?? "public") === "public"
        ? ((await opts.publicSource(ds.name)) ?? []).filter((r) => schema.safeParse(r).success)
        : [];
    const from = fromProd.length > 0 ? "production" : "made-up";
    const rows = (
      from === "production" ? fromProd : fakeRows(schema, MADE_UP_ROWS, seed)
    ) as Record<string, unknown>[];
    const cols = Object.keys(schema.shape);
    const insert = `insert or replace into ${ds.table} (${cols.join(",")}) values (${cols.map(() => "?").join(",")})`;
    await d1.batch([
      d1.prepare(`delete from ${ds.table}`),
      ...rows.map((r) => d1.prepare(insert).bind(...cols.map((k) => r[k]))),
    ] as never[]);
    out.push({ dataset: ds.name, from, rows: rows.length });
  }
  return out;
}
