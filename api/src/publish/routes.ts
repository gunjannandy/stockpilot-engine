// The publishing door (decisions §2): rows arrive tagged with a run id and their provenance, are
// staged, and become what screens read only when the run finishes and its checks pass, by moving the
// dataset's pointer in one write. A failed run leaves the last good run served.
import {
  D1_DAILY_WRITES,
  type Dataset,
  DOOR_WRITE_SHARE,
  PublishFinishRequest,
  PublishRowsRequest,
  ROWS_LIMIT,
} from "@stockpilot/contract";
import { Hono } from "hono";
import { type Ctx, istDay, istText, rawBody } from "../app";
import { type Datasets, defaultDatasets, forget, lookup } from "./lib";

const IDENT = /^[a-z][a-z0-9_]*$/;
const HELD_KEPT = 200;
const CHUNK = 20;

type RunRow = {
  status: string;
  as_of: string;
  accepted: number;
  held: number;
  refused: number;
};

const parse = (raw: string): unknown => {
  try {
    return JSON.parse(raw);
  } catch {
    return undefined;
  }
};

/** First reason a row fails: its schema, then the dataset's own row check. */
function holdReason(
  ds: Dataset,
  row: Record<string, unknown>,
): { ok: true; row: Record<string, unknown> } | { ok: false; reason: string } {
  const p = ds.row.safeParse(row);
  if (!p.success) {
    const i = p.error.issues[0];
    return { ok: false, reason: `${i?.path.join(".") || "row"}: ${i?.message ?? "invalid"}` };
  }
  const data = p.data as Record<string, unknown>;
  const reason = ds.rowCheck?.(data) ?? null;
  return reason ? { ok: false, reason } : { ok: true, row: data };
}

export function publishRoutes(ctx: Ctx, all: Datasets = defaultDatasets) {
  const app = new Hono();
  const door = (name: string) => {
    const ds = lookup(all, name);
    return ds && IDENT.test(ds.table) ? ds : undefined;
  };
  const doorUsedToday = async (day: string) => {
    const r = (await ctx.d1
      .prepare("select coalesce(sum(writes), 0) as n from write_budget where day = ?")
      .bind(day)
      .first()) as { n: number } | null;
    return r?.n ?? 0;
  };
  const run = async (dataset: string, runId: string) =>
    (await ctx.d1
      .prepare(
        "select status, as_of, accepted, held, refused from runs where dataset = ? and run_id = ?",
      )
      .bind(dataset, runId)
      .first()) as RunRow | null;

  app.post("/api/publish/rows", ctx.guard.ingest, async (c) => {
    const req = PublishRowsRequest.safeParse(parse(rawBody(c)));
    if (!req.success) {
      const i = req.error.issues[0];
      return c.json(
        { error: `bad body: ${i?.path.join(".") || "body"} ${i?.message ?? ""}`.trim() },
        400,
      );
    }
    const b = req.data;
    const ds = door(b.dataset);
    if (!ds) return c.json({ error: "dataset not allowed" }, 403);
    if (ds.delivery === "file")
      return c.json({ error: "this dataset publishes one file per run, not rows" }, 422);

    const day = istDay(ctx.now());
    const existing = await run(ds.name, b.run_id);
    if (existing && existing.status !== "running")
      return c.json({ error: "run already finished" }, 409);
    const base = (existing?.accepted ?? 0) + (existing?.held ?? 0) + (existing?.refused ?? 0);
    const limit = ds.rowsLimit ?? ROWS_LIMIT;
    if ((existing?.accepted ?? 0) + b.rows.length > limit)
      return c.json({ error: `over ${limit} rows: publish one file per run instead` }, 413);

    // Row checks hold a row back with its reason; the run goes on.
    const good: { seq: number; row: Record<string, unknown> }[] = [];
    const held: { seq: number; reason: string; row: unknown }[] = [];
    b.rows.forEach((r, i) => {
      const v = holdReason(ds, r);
      if (v.ok) good.push({ seq: base + i, row: v.row });
      else held.push({ seq: base + i, reason: v.reason, row: r });
    });

    const dayUsed =
      (
        (await ctx.d1
          .prepare("select writes from write_budget where day = ? and dataset = ?")
          .bind(day, ds.name)
          .first()) as { writes: number } | null
      )?.writes ?? 0;
    const room = Math.max(0, ds.writeBudget - dayUsed);
    const doorRoom = Math.max(
      0,
      Math.floor(D1_DAILY_WRITES * DOOR_WRITE_SHARE) - (await doorUsedToday(day)),
    );
    const keptHeld = held.slice(0, HELD_KEPT);
    const take = good.slice(0, Math.max(0, Math.min(room, doorRoom) - keptHeld.length));
    const refused = good.length - take.length;

    const statements = [
      ctx.d1
        .prepare(
          "insert into runs (dataset, run_id, status, source, fetched_at, as_of, started_at) values (?, ?, 'running', ?, ?, ?, ?) on conflict(dataset, run_id) do nothing",
        )
        .bind(ds.name, b.run_id, b.source, b.fetched_at, b.as_of, istText(ctx.now())),
    ];
    for (let i = 0; i < take.length; i += CHUNK) {
      const part = take.slice(i, i + CHUNK);
      statements.push(
        ctx.d1
          .prepare(
            `insert or replace into dataset_rows (dataset, run_id, seq, body) values ${part.map(() => "(?, ?, ?, ?)").join(", ")}`,
          )
          .bind(...part.flatMap((r) => [ds.name, b.run_id, r.seq, JSON.stringify(r.row)])),
      );
    }
    for (const h of keptHeld)
      statements.push(
        ctx.d1
          .prepare(
            "insert or replace into held_rows (dataset, run_id, seq, reason, body) values (?, ?, ?, ?, ?)",
          )
          .bind(ds.name, b.run_id, h.seq, h.reason, JSON.stringify(h.row).slice(0, 2000)),
      );
    statements.push(
      ctx.d1
        .prepare(
          "update runs set accepted = accepted + ?, held = held + ?, refused = refused + ? where dataset = ? and run_id = ?",
        )
        .bind(take.length, held.length, refused, ds.name, b.run_id),
    );
    const spent = take.length + keptHeld.length;
    if (spent > 0)
      statements.push(
        ctx.d1
          .prepare(
            "insert into write_budget (day, dataset, writes) values (?, ?, ?) on conflict(day, dataset) do update set writes = writes + excluded.writes",
          )
          .bind(day, ds.name, spent),
      );
    await ctx.d1.batch(statements);

    if (refused > 0 && take.length === 0)
      return c.json({ error: "daily write budget reached", held_back: held.length }, 429);
    return c.json({ accepted: take.length, held_back: held.length + refused });
  });

  app.post("/api/publish/finish", ctx.guard.ingest, async (c) => {
    const req = PublishFinishRequest.safeParse(parse(rawBody(c)));
    if (!req.success) return c.json({ error: "bad body" }, 400);
    const b = req.data;
    const ds = door(b.dataset);
    if (!ds) return c.json({ error: "dataset not allowed" }, 403);
    const isFile = ds.delivery === "file";
    if (isFile !== Boolean(b.file))
      return c.json(
        {
          error: isFile
            ? "this dataset publishes one file per run"
            : "this dataset publishes rows, not a file",
        },
        422,
      );

    let r = await run(ds.name, b.run_id);
    if (isFile && !r) {
      if (!b.source || !b.fetched_at || !b.as_of)
        return c.json({ error: "bad body: a file run needs source, fetched_at and as_of" }, 400);
      await ctx.d1
        .prepare(
          "insert into runs (dataset, run_id, status, source, fetched_at, as_of, started_at) values (?, ?, 'running', ?, ?, ?, ?)",
        )
        .bind(ds.name, b.run_id, b.source, b.fetched_at, b.as_of, istText(ctx.now()))
        .run();
      r = await run(ds.name, b.run_id);
    }
    if (!r) return c.json({ error: "no such run" }, 404);
    if (r.status !== "running") return c.json({ error: "run already finished" }, 409);

    // The run's verdict: a reason fails it and leaves the last good run served.
    const held = isFile ? (b.held_back ?? 0) : r.held;
    const rowCount = isFile ? (b.file?.rows ?? 0) : r.accepted;
    let reason: string | null = null;
    if (b.file && b.file.name !== `${ds.name}.${b.file.sha256.slice(0, 12)}.json`)
      reason = "the file's name does not carry its hash";
    else if (r.refused > 0) reason = `${r.refused} rows were refused by the write budget`;
    else if (rowCount === 0) reason = "the run holds no rows";
    else if (held + rowCount > 0 && held / (held + rowCount) > (ds.heldBackLimit ?? 0.2))
      reason = `${held} of ${held + rowCount} rows were held back, over the limit`;
    if (!reason && ds.runCheck) {
      const rows = isFile
        ? undefined
        : (
            (await ctx.d1
              .prepare(
                "select body from dataset_rows where dataset = ? and run_id = ? order by seq",
              )
              .bind(ds.name, b.run_id)
              .all()) as {
              results: { body: string }[];
            }
          ).results.map((x) => JSON.parse(x.body) as Record<string, unknown>);
      reason = ds.runCheck({ rowCount, rows, summary: b.summary ?? {} });
    }

    const serving = async () => {
      const p = (await ctx.d1
        .prepare("select run_id, as_of from pointers where dataset = ?")
        .bind(ds.name)
        .first()) as { run_id: string; as_of: string } | null;
      return p ? { run_id: p.run_id, as_of: p.as_of } : null;
    };
    const now = istText(ctx.now());
    if (reason) {
      await ctx.d1.batch([
        ctx.d1
          .prepare(
            "update runs set status = 'failed', error = ?, finished_at = ? where dataset = ? and run_id = ?",
          )
          .bind(reason, now, ds.name, b.run_id),
        ctx.d1
          .prepare("delete from dataset_rows where dataset = ? and run_id = ?")
          .bind(ds.name, b.run_id),
      ]);
      return c.json({ published: false, run_id: b.run_id, reason, serving: await serving() }, 422);
    }

    const summary = JSON.stringify({ rows: rowCount, held_back: held, ...(b.summary ?? {}) });
    await ctx.d1.batch([
      // The one write that moves what screens read.
      ctx.d1
        .prepare(
          `insert into pointers (dataset, run_id, previous_run_id, as_of, published_at, rows, file, summary)
           values (?, ?, null, ?, ?, ?, ?, ?)
           on conflict(dataset) do update set previous_run_id = pointers.run_id, run_id = excluded.run_id,
             as_of = excluded.as_of, published_at = excluded.published_at, rows = excluded.rows,
             file = excluded.file, summary = excluded.summary`,
        )
        .bind(ds.name, b.run_id, r.as_of, now, rowCount, b.file?.name ?? null, summary),
      ctx.d1
        .prepare(
          "update runs set status = 'published', finished_at = ? where dataset = ? and run_id = ?",
        )
        .bind(now, ds.name, b.run_id),
      // Keep the current and the previous run (for change marks); older rows go.
      ctx.d1
        .prepare(
          "delete from dataset_rows where dataset = ? and run_id not in (select run_id from pointers where dataset = ? union select previous_run_id from pointers where dataset = ? and previous_run_id is not null)",
        )
        .bind(ds.name, ds.name, ds.name),
    ]);
    forget(ctx, ds.name);
    return c.json({ published: true, run_id: b.run_id, reason: null, serving: await serving() });
  });

  // For Admin: each dataset's current run and the rows held back with their reasons.
  app.get("/api/publish/runs", ctx.guard.person, async (c) => {
    const pointers = (await ctx.d1.prepare("select * from pointers order by dataset").all()) as {
      results: unknown[];
    };
    const recent = (await ctx.d1
      .prepare("select * from runs order by started_at desc limit 50")
      .all()) as { results: unknown[] };
    return c.json({ pointers: pointers.results, runs: recent.results });
  });
  app.get("/api/publish/held/:dataset", ctx.guard.person, async (c) => {
    const rows = (await ctx.d1
      .prepare(
        "select run_id, seq, reason, body from held_rows where dataset = ? order by run_id desc, seq limit 200",
      )
      .bind(c.req.param("dataset"))
      .all()) as { results: unknown[] };
    return c.json({ held: rows.results });
  });

  return app;
}

export default function routes(ctx: Ctx) {
  return publishRoutes(ctx);
}
