// Reading what was published: a dataset's current run to the screens, and the engine's release
// files passed through with content-hashed names and year-long caching. The bundle holds no data.
import { Hono } from "hono";
import type { Ctx } from "../app";
import { type Datasets, defaultDatasets, lookup, servePane } from "../publish/lib";

export const DATA_BASE =
  "https://github.com/stockpilot-hq/stockpilot-engine/releases/download/data";
export const FILE_NAME = /^[a-z][a-z0-9_]*\.[0-9a-f]{12}\.json$/;

export function dataRoutes(ctx: Ctx, opts: { datasets?: Datasets; fetch?: typeof fetch } = {}) {
  const all = opts.datasets ?? defaultDatasets;
  const app = new Hono();

  app.get("/api/data/:dataset", ctx.guard.person, async (c) => {
    const ds = lookup(all, c.req.param("dataset"));
    if (!ds) return c.json({ error: "no such dataset" }, 404);
    const previous = c.req.query("run") === "previous";
    return servePane(
      ctx,
      c,
      ds,
      async (p) => {
        const runId = previous ? p?.previousRunId : p?.runId;
        const rows =
          runId && !p?.file
            ? (
                (await ctx.d1
                  .prepare(
                    "select body from dataset_rows where dataset = ? and run_id = ? order by seq",
                  )
                  .bind(ds.name, runId)
                  .all()) as { results: { body: string }[] }
              ).results.map((x) => JSON.parse(x.body) as unknown)
            : [];
        return {
          dataset: ds.name,
          run_id: runId ?? null,
          as_of: p?.asOf ?? null,
          published_at: p?.publishedAt ?? null,
          rows,
          file: p?.file ? `/data/${p.file}` : null,
          summary: p?.summary ?? {},
        };
      },
      previous ? "previous" : "",
    );
  });

  app.get("/data/:file", async (c) => {
    const name = c.req.param("file");
    if (!FILE_NAME.test(name)) return c.json({ error: "not found" }, 404);
    const base = (ctx.env as Record<string, string | undefined>).DATA_BASE_URL ?? DATA_BASE;
    const up = await (opts.fetch ?? fetch)(`${base}/${name}`);
    if (!up.ok)
      return new Response(JSON.stringify({ error: "not found" }), {
        status: 404,
        headers: { "cache-control": "no-store", "content-type": "application/json" },
      });
    return new Response(up.body, {
      headers: {
        "content-type": "application/json",
        // The name carries the content's hash, so the file never changes under it.
        "cache-control": "public, max-age=31536000, immutable",
      },
    });
  });

  return app;
}

export default function routes(ctx: Ctx) {
  return dataRoutes(ctx);
}
