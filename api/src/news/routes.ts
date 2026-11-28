// News: the append-only impact door (Job only), ranked cards, and one stock's news. Impact rows are only ever
// inserted; a second write of the same item and stock is ignored and the triggers refuse update and delete.
import {
  NewsImpactRequest,
  type NewsItemRow,
  type NewsResponse,
  newsImpactRowCheck,
} from "@stockpilot/contract";
import { Hono } from "hono";
import { type Ctx, istText, rawBody } from "../app";
import { readImpact } from "./impact";

const WEEK_MS = 7 * 86400_000;

export default function routes(ctx: Ctx) {
  const app = new Hono();

  const currentItems = async (): Promise<NewsItemRow[]> => {
    const p = (await ctx.d1
      .prepare("select run_id from pointers where dataset = 'news_items'")
      .first()) as { run_id: string } | null;
    if (!p) return [];
    const r = (await ctx.d1
      .prepare(
        "select body from dataset_rows where dataset = 'news_items' and run_id = ? order by seq",
      )
      .bind(p.run_id)
      .all()) as { results: { body: string }[] };
    return r.results.map((x) => JSON.parse(x.body) as NewsItemRow);
  };

  app.post("/api/news/impact", ctx.guard.ingest, async (c) => {
    let body: unknown;
    try {
      body = JSON.parse(rawBody(c));
    } catch {
      return c.json({ error: "bad body" }, 400);
    }
    const req = NewsImpactRequest.safeParse(body);
    if (!req.success) return c.json({ error: "bad body" }, 400);
    const held: { id: string; reason: string }[] = [];
    const ok = req.data.rows.filter((r) => {
      const reason = newsImpactRowCheck(r);
      if (reason) held.push({ id: r.id, reason });
      return !reason;
    });
    let written = 0;
    for (const r of ok) {
      const res = (await ctx.d1
        .prepare(
          "insert or ignore into news_impact (id, item_id, symbol, exchange, relation, direction, size, sector_only, why_en, why_bn, weight, judged_at) values (?,?,?,?,?,?,?,?,?,?,?,?)",
        )
        .bind(
          r.id,
          r.item_id,
          r.symbol,
          r.exchange,
          r.relation,
          r.direction,
          r.size,
          r.sector_only ? 1 : 0,
          r.why_en,
          r.why_bn,
          r.weight,
          r.judged_at,
        )
        .run()) as { meta?: { changes?: number } };
      written += res.meta?.changes ?? 0;
    }
    const at = istText(ctx.now());
    for (const id of req.data.judged_ids)
      await ctx.d1
        .prepare("insert or ignore into news_judged (item_id, at) values (?, ?)")
        .bind(id, at)
        .run();
    return c.json({ written, ignored: ok.length - written, held });
  });

  app.get("/api/news/judged", ctx.guard.ingest, async (c) => {
    const r = (await ctx.d1
      .prepare("select item_id from news_judged order by at desc limit 5000")
      .all()) as { results: { item_id: string }[] };
    return c.json({ item_ids: r.results.map((x) => x.item_id) });
  });

  app.get("/api/news", ctx.guard.person, async (c) => {
    const items = await currentItems();
    const impacts = await readImpact(ctx.d1, {
      since: new Date(ctx.now().getTime() - WEEK_MS).toISOString(),
    });
    const out: NewsResponse = {
      items: items.map((i) => ({ ...i, impacts: impacts.filter((x) => x.item_id === i.id) })),
    };
    return c.json(out);
  });

  app.get("/api/news/stock/:symbol", ctx.guard.person, async (c) => {
    const symbol = c.req.param("symbol").toUpperCase();
    const impacts = await readImpact(ctx.d1, { symbols: [symbol], limit: 50 });
    const items = new Map((await currentItems()).map((i) => [i.id, i]));
    return c.json({
      symbol,
      news: impacts.flatMap((x) => {
        const item = items.get(x.item_id);
        return item ? [{ ...item, impact: x }] : [];
      }),
    });
  });

  return app;
}
