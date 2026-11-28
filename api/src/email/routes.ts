// GET /api/email/owner and /api/email/father: the 08:45 IST morning email as HTML for the Apps Script to send.
// Behind the shared secret the Apps Script already holds. Other areas' sections arrive through `sections`.
import type { CalendarRow, NewsImpactRow } from "@stockpilot/contract";
import { Hono } from "hono";
import { type Ctx, istDay } from "../app";
import { readImpact } from "../news/impact";
import { type EmailData, renderEmail } from "./render";

type Db = Ctx["d1"];

/** Mood from the direction of the impact rows alone (sector-only rows carry none). */
export function mood(rows: { direction: string | null; sector_only?: boolean }[]): string | null {
  const dir = rows.filter((r) => !r.sector_only && r.direction);
  if (!dir.length) return null;
  const good = dir.filter((r) => r.direction === "good").length;
  const bad = dir.filter((r) => r.direction === "bad").length;
  if (good > bad * 1.5) return "Mostly good news";
  if (bad > good * 1.5) return "Mostly bad news";
  return "Mixed news";
}

/** Calendar rows from `from` to `to` (inclusive), as short lines. */
export async function upcoming(d1: Db, from: string, to: string): Promise<string[]> {
  const p = (await d1
    .prepare("select run_id from pointers where dataset = 'calendar'")
    .first()) as {
    run_id: string;
  } | null;
  if (!p) return [];
  const rows = (
    (await d1
      .prepare(
        "select body from dataset_rows where dataset = 'calendar' and run_id = ? order by seq",
      )
      .bind(p.run_id)
      .all()) as { results: { body: string }[] }
  ).results.map((r) => JSON.parse(r.body) as CalendarRow);
  return rows
    .filter((r) => r.date >= from && r.date <= to)
    .sort((a, b) => a.date.localeCompare(b.date))
    .map(
      (r) =>
        `${r.date}: ${r.kind.replace("_", " ")}${r.symbol ? ` ${r.symbol}` : ""}${r.reason ? ` (${r.reason})` : ""}`,
    );
}

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
    const comingUp = await upcoming(
      ctx.d1,
      istDay(ctx.now()),
      istDay(new Date(ctx.now().getTime() + 7 * 86400_000)),
    );
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
      mood: mood(impacts),
      comingUp,
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
