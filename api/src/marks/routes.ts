// Change marks: a row is marked when it differs between a dataset's previous and current run, so
// marks follow from publishing with no Job of their own. "Seen" is one shared row per dataset row
// and run: opening a row clears it for both of us.
import { diffRows, hasNews, type MarksAnswer, SeenBody } from "@stockpilot/contract";
import { Hono } from "hono";
import { type Ctx, istText } from "../app";
import { type Datasets, defaultDatasets, lookup } from "../publish/lib";

type Body = { body: string };

async function rowsOf(ctx: Ctx, dataset: string, runId: string) {
  const r = (await ctx.d1
    .prepare("select body from dataset_rows where dataset = ? and run_id = ? order by seq")
    .bind(dataset, runId)
    .all()) as { results: Body[] };
  return r.results.map((x) => JSON.parse(x.body) as Record<string, unknown>);
}

export async function computeMarks(
  ctx: Ctx,
  all: Datasets = defaultDatasets,
): Promise<MarksAnswer> {
  const ptrs = (await ctx.d1.prepare("select * from pointers").all()) as {
    results: {
      dataset: string;
      run_id: string;
      previous_run_id: string | null;
      file: string | null;
    }[];
  };
  const seen = new Set(
    (
      (await ctx.d1.prepare("select dataset, row_key, run_id from mark_seen").all()) as {
        results: { dataset: string; row_key: string; run_id: string }[];
      }
    ).results.map((s) => `${s.dataset}\u0000${s.row_key}\u0000${s.run_id}`),
  );
  const items: MarksAnswer["items"] = [];
  const news: MarksAnswer["news"] = [];
  for (const p of ptrs.results) {
    // Only `rows` datasets are compared here; a file dataset's change marks come with its own pane.
    if (!lookup(all, p.dataset) || p.file) continue;
    const current = await rowsOf(ctx, p.dataset, p.run_id);
    const previous = p.previous_run_id ? await rowsOf(ctx, p.dataset, p.previous_run_id) : null;
    const changed = diffRows(previous, current);
    const changedKeys = new Set(changed.map((c) => c.key));
    for (const c of changed)
      items.push({
        dataset: p.dataset,
        key: c.key,
        runId: p.run_id,
        fields: c.fields,
        isNew: c.isNew,
        seen: seen.has(`${p.dataset}\u0000${c.key}\u0000${p.run_id}`),
      });
    for (const r of current) {
      const key = (r.symbol ?? r.id) as string | undefined;
      if (key && hasNews(r) && !changedKeys.has(key)) news.push({ dataset: p.dataset, key });
    }
  }
  return { items, unseen: items.filter((i) => !i.seen).length, news };
}

export function marksRoutes(ctx: Ctx, opts: { datasets?: Datasets } = {}) {
  const all = opts.datasets ?? defaultDatasets;
  const app = new Hono();
  app.get("/api/marks", ctx.guard.person, async (c) => c.json(await computeMarks(ctx, all)));
  app.post("/api/marks/seen", ctx.guard.person, async (c) => {
    const body = SeenBody.safeParse(await c.req.json().catch(() => undefined));
    if (!body.success) return c.json({ error: "say a dataset and key, or all" }, 400);
    const who = (c as unknown as { get(k: string): string | undefined }).get("person") ?? null;
    const at = istText(ctx.now());
    const answer = await computeMarks(ctx, all);
    const todo = answer.items.filter(
      (i) =>
        !i.seen &&
        ("all" in body.data || (i.dataset === body.data.dataset && i.key === body.data.key)),
    );
    for (const i of todo)
      await ctx.d1
        .prepare(
          "insert or ignore into mark_seen (dataset, row_key, run_id, seen_at, by_person) values (?, ?, ?, ?, ?)",
        )
        .bind(i.dataset, i.key, i.runId, at, who)
        .run();
    return c.json({ marked: todo.length });
  });
  return app;
}

export default (ctx: Ctx) => marksRoutes(ctx);
