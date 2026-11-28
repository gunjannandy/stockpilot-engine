// GET /api/email/owner and /api/email/father: the 08:45 IST morning email as HTML for the Apps Script to send.
// Behind the shared secret the Apps Script already holds. Other areas' sections arrive through `sections`.
import type { NewsImpactRow } from "@stockpilot/contract";
import { Hono } from "hono";
import { type Ctx, istDay } from "../app";
import { readImpact } from "../news/impact";
import { type EmailData, renderEmail } from "./render";

export default function routes(ctx: Ctx) {
  const app = new Hono();

  async function data(): Promise<EmailData> {
    const since = new Date(ctx.now().getTime() - 36 * 3600_000).toISOString();
    const impacts = await readImpact(ctx.d1, { since, limit: 200 });
    const p = (await ctx.d1
      .prepare("select run_id from pointers where dataset = 'news_items'")
      .first()) as {
      run_id: string;
    } | null;
    const rows = p
      ? (
          (await ctx.d1
            .prepare(
              "select body from dataset_rows where dataset = 'news_items' and run_id = ? order by seq limit 8",
            )
            .bind(p.run_id)
            .all()) as { results: { body: string }[] }
        ).results.map((r) => JSON.parse(r.body) as { id: string; title: string; link: string })
      : [];
    const by = new Map<string, NewsImpactRow[]>();
    for (const i of impacts) by.set(i.item_id, [...(by.get(i.item_id) ?? []), i]);
    const health = await ctx
      .call("/api/health", { headers: { "x-health-secret": ctx.env.HEALTH_SECRET ?? "" } })
      .then(
        async (r) => (r.ok ? { ok: true, line: "Everything is running" } : null),
        () => null,
      );
    return {
      date: istDay(ctx.now()),
      news: rows.map((n) => ({
        ...n,
        stocks: (by.get(n.id) ?? []).map((i) => ({
          symbol: i.symbol,
          direction: i.sector_only ? null : i.direction,
        })),
      })),
      health,
    };
  }

  for (const who of ["owner", "father"] as const)
    app.get(`/api/email/${who}`, ctx.guard.secret, async (c) =>
      c.html(renderEmail(await data(), who)),
    );

  return app;
}
