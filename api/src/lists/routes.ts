// Lists: Worth following (the lists dataset with each stock's call), the screen's counts, the watchlist, star and
// Not now. A star and a Not now are direct row writes here, with no Job row (checks/C-052-1); Not now rows end after
// a week or a month and Undo removes them (checks/C-053-1). The Job-only route gives the lists Job today's movers.
import {
  BUSY_MOVE_PCT,
  type CallView,
  confidenceLine,
  type ListRow,
  type ListsResponse,
  NOT_NOW_FOR,
  NotNowRequest,
  PUBLIC_LISTS,
  StarRequest,
  type WatchlistResponse,
} from "@stockpilot/contract";
import { Hono } from "hono";
import { type Ctx, istText } from "../app";
import { currentPointer } from "../publish/lib";

const DAY_MS = 86400_000;
type RawCall = Omit<CallView, "limited" | "confidence"> & { limited: number };

export default function routes(ctx: Ctx) {
  const app = new Hono();

  const callsOf = async (symbols: string[]): Promise<Map<string, CallView>> => {
    const out = new Map<string, CallView>();
    if (!symbols.length) return out;
    const r = (await ctx.d1
      .prepare(
        `select c.* from calls c join (select exchange, symbol, max(made_on) as m from calls where symbol in (${symbols.map(() => "?").join(",")}) group by exchange, symbol) l on l.exchange = c.exchange and l.symbol = c.symbol and l.m = c.made_on order by c.horizon_days desc`,
      )
      .bind(...symbols)
      .all()) as { results: RawCall[] };
    for (const x of r.results)
      out.set(x.symbol, {
        ...x,
        limited: x.limited === 1,
        confidence: confidenceLine(x.similar_n, x.similar_beat),
      });
    return out;
  };

  app.get("/api/lists", ctx.guard.person, async (c) => {
    const p = await currentPointer(ctx, "lists");
    const rows = p
      ? (
          (await ctx.d1
            .prepare(
              "select body from dataset_rows where dataset = 'lists' and run_id = ? order by seq",
            )
            .bind(p.runId)
            .all()) as { results: { body: string }[] }
        ).results.map((x) => JSON.parse(x.body) as ListRow)
      : [];
    const calls = await callsOf([...new Set(rows.map((r) => r.symbol))]);
    const screen = await currentPointer(ctx, "screen");
    const analysed = Number(screen?.summary.analysed);
    const passed = Number(screen?.summary.passed);
    const out: ListsResponse = {
      counts:
        screen && Number.isFinite(analysed) && Number.isFinite(passed)
          ? { analysed, passed, as_of: screen.asOf }
          : null,
      lists: PUBLIC_LISTS.map((list) => {
        const mine = rows.filter((r) => r.list === list).sort((a, b) => a.position - b.position);
        return {
          list,
          updated_at: mine.reduce<ListRow["updated_at"] | null>(
            (m, r) => (m && m > r.updated_at ? m : r.updated_at),
            null,
          ),
          rows: mine.map((r) => ({ ...r, call: calls.get(r.symbol) ?? null })),
        };
      }),
    };
    return c.json(out);
  });

  /** What the lists Job reads (Job only): the latest screen file, the latest calls, and today's movers among the quotes we hold. */
  app.get("/api/lists/inputs", ctx.guard.ingest, async (c) => {
    const screen = await currentPointer(ctx, "screen");
    const movers = (
      (await ctx.d1
        .prepare(
          "select symbol, price, prev_close from quote_cache where prev_close is not null and prev_close > 0",
        )
        .all()) as { results: { symbol: string; price: number; prev_close: number }[] }
    ).results
      .map((q) => ({ symbol: q.symbol, move_pct: (q.price / q.prev_close - 1) * 100 }))
      .filter((q) => Math.abs(q.move_pct) >= BUSY_MOVE_PCT)
      .sort((a, b) => Math.abs(b.move_pct) - Math.abs(a.move_pct));
    const calls = (
      (await ctx.d1
        .prepare(
          "select c.symbol, c.exchange, c.verdict, c.chance from calls c join (select exchange, symbol, max(made_on) as m from calls group by exchange, symbol) l on l.exchange = c.exchange and l.symbol = c.symbol and l.m = c.made_on where c.horizon_days = 63",
        )
        .all()) as {
        results: { symbol: string; exchange: string; verdict: string; chance: number | null }[];
      }
    ).results;
    return c.json({
      screen: screen?.file ? { file: `/data/${screen.file}`, as_of: screen.asOf } : null,
      calls,
      movers,
    });
  });

  app.get("/api/watchlist", ctx.guard.person, async (c) => {
    const now = istText(ctx.now());
    const items = (
      (await ctx.d1
        .prepare("select id, kind, name, added_at from watchlist order by added_at desc")
        .all()) as {
        results: { id: string; kind: "stock" | "fund"; name: string | null; added_at: string }[];
      }
    ).results;
    const calls = await callsOf(items.filter((i) => i.kind === "stock").map((i) => i.id));
    const notNow = (
      (await ctx.d1
        .prepare("select symbol, until, created_at from not_now where until > ? order by until")
        .bind(now)
        .all()) as { results: { symbol: string; until: string; created_at: string }[] }
    ).results;
    const out = {
      items: items.map((i) => ({ ...i, call: calls.get(i.id) ?? null })),
      not_now: notNow,
    } as WatchlistResponse;
    return c.json(out);
  });

  app.post("/api/watchlist", ctx.guard.person, async (c) => {
    const body: unknown = await c.req.json().catch(() => undefined);
    const req = StarRequest.safeParse(body);
    if (!req.success) return c.json({ error: "bad body" }, 400);
    const id = req.data.kind === "stock" ? req.data.id.toUpperCase() : req.data.id;
    await ctx.d1
      .prepare("insert or ignore into watchlist (id, kind, name, added_at) values (?, ?, ?, ?)")
      .bind(id, req.data.kind, req.data.name ?? null, istText(ctx.now()))
      .run();
    return c.json({ id, starred: true });
  });

  /** Un-star; the screen's Undo is a second POST. */
  app.delete("/api/watchlist/:id", ctx.guard.person, async (c) => {
    const raw = c.req.param("id");
    await ctx.d1
      .prepare("delete from watchlist where id = ? or id = ?")
      .bind(raw, raw.toUpperCase())
      .run();
    return c.json({ id: raw, starred: false });
  });

  app.post("/api/not-now", ctx.guard.person, async (c) => {
    const body: unknown = await c.req.json().catch(() => undefined);
    const req = NotNowRequest.safeParse(body);
    if (!req.success) return c.json({ error: "bad body" }, 400);
    const now = ctx.now();
    const symbol = req.data.symbol.toUpperCase();
    const until = istText(new Date(now.getTime() + NOT_NOW_FOR[req.data.for] * DAY_MS));
    await ctx.d1
      .prepare(
        "insert into not_now (symbol, until, created_at) values (?, ?, ?) on conflict(symbol) do update set until = excluded.until, created_at = excluded.created_at",
      )
      .bind(symbol, until, istText(now))
      .run();
    return c.json({ symbol, until });
  });

  /** Undo removes the Not now row. */
  app.delete("/api/not-now/:symbol", ctx.guard.person, async (c) => {
    const symbol = c.req.param("symbol").toUpperCase();
    await ctx.d1.prepare("delete from not_now where symbol = ?").bind(symbol).run();
    return c.json({ symbol, hidden: false });
  });

  return app;
}
