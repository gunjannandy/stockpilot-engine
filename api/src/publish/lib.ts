// Shared by the publishing door and every pane: the registry lookup, each dataset's current-run
// pointer (cached a short while, so a repeat visit costs no D1 read) and the pane answer helper
// (ETag = run id, 304 with no read, edge cache when the platform has one).
import { type Dataset, datasets as registry } from "@stockpilot/contract";
import type { Context } from "hono";
import type { Ctx } from "../app";

export type Datasets = Record<string, Dataset>;
export const defaultDatasets = registry as unknown as Datasets;

export const lookup = (all: Datasets, name: string): Dataset | undefined =>
  Object.hasOwn(all, name) ? all[name] : undefined;

export type Pointer = {
  dataset: string;
  runId: string;
  previousRunId: string | null;
  asOf: string;
  publishedAt: string;
  rows: number;
  file: string | null;
  summary: Record<string, unknown>;
};

/** How long a pointer read is reused. Another isolate's publish shows up at most this late. */
export const POINTER_TTL_MS = 30_000;

type Memory = {
  pointers: Map<string, { at: number; p: Pointer | null }>;
  panes: Map<string, Response>;
};
const memories = new WeakMap<object, Memory>();
const memoryOf = (ctx: Ctx): Memory => {
  let m = memories.get(ctx.d1);
  if (!m) {
    m = { pointers: new Map(), panes: new Map() };
    memories.set(ctx.d1, m);
  }
  return m;
};

type PointerRow = {
  dataset: string;
  run_id: string;
  previous_run_id: string | null;
  as_of: string;
  published_at: string;
  rows: number;
  file: string | null;
  summary: string;
};

export async function currentPointer(ctx: Ctx, dataset: string): Promise<Pointer | null> {
  const mem = memoryOf(ctx);
  const hit = mem.pointers.get(dataset);
  if (hit && ctx.now().getTime() - hit.at < POINTER_TTL_MS) return hit.p;
  const r = await ctx.d1.prepare("select * from pointers where dataset = ?").bind(dataset).first();
  const row = r as PointerRow | null;
  const p: Pointer | null = row
    ? {
        dataset: row.dataset,
        runId: row.run_id,
        previousRunId: row.previous_run_id,
        asOf: row.as_of,
        publishedAt: row.published_at,
        rows: row.rows,
        file: row.file,
        summary: JSON.parse(row.summary) as Record<string, unknown>,
      }
    : null;
  mem.pointers.set(dataset, { at: ctx.now().getTime(), p });
  return p;
}

/** Called when a run is published: this isolate forgets the old pointer and answers at once. */
export function forget(ctx: Ctx, dataset: string) {
  const mem = memoryOf(ctx);
  mem.pointers.delete(dataset);
  for (const k of mem.panes.keys()) if (k.startsWith(`${dataset}/`)) mem.panes.delete(k);
}

export const etagOf = (dataset: string, runId: string) => `"${dataset}-${runId}"`;

const edge = ():
  | { match(k: string): Promise<Response | undefined>; put(k: string, r: Response): Promise<void> }
  | undefined => (globalThis as { caches?: { default?: never } }).caches?.default;

/**
 * Answer a pane from one dataset's current run. The run id is the ETag: a browser holding it gets a
 * 304 and nothing is read. The built answer is kept (edge cache where it works, else this isolate)
 * under the run id, so it is served until the pointer moves. `variant` names the pane's own query.
 */
export async function servePane(
  ctx: Ctx,
  c: Context,
  dataset: Dataset,
  render: (p: Pointer | null) => Promise<unknown>,
  variant = "",
): Promise<Response> {
  const p = await currentPointer(ctx, dataset.name);
  const headers = { "cache-control": "private, no-cache", "content-type": "application/json" };
  if (p) {
    const tag = etagOf(dataset.name, p.runId);
    if (c.req.header("if-none-match") === tag)
      return new Response(null, {
        status: 304,
        headers: { etag: tag, "cache-control": headers["cache-control"] },
      });
    const key = `${dataset.name}/${p.runId}/${variant}`;
    const mem = memoryOf(ctx);
    const e = dataset.visibility === "private" ? undefined : edge();
    const kept = mem.panes.get(key) ?? (await e?.match(`https://pane.invalid/${key}`));
    if (kept) return kept.clone();
    const res = new Response(JSON.stringify(await render(p)), {
      headers: { ...headers, etag: tag },
    });
    if (mem.panes.size > 200) mem.panes.clear();
    mem.panes.set(key, res.clone());
    await e?.put(`https://pane.invalid/${key}`, res.clone());
    return res;
  }
  return new Response(JSON.stringify(await render(null)), { headers });
}
