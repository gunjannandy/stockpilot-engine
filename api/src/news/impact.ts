// The one way to read news impact. Every consumer (refresh triggers, forecast levels and bands, change marks,
// In today's news, near-live picks, exposure, the nightly note) reads through here, never the raw sector tag.
import type { NewsImpactRow } from "@stockpilot/contract";
import type { D1Like } from "../app";

type Raw = Omit<NewsImpactRow, "sector_only"> & { sector_only: number };
const shape = (r: Raw): NewsImpactRow => ({ ...r, sector_only: r.sector_only === 1 });

/** Impact rows for these stocks (all stocks when none given) judged at or after `since`, newest first. */
export async function readImpact(
  d1: D1Like,
  opts: { symbols?: string[]; since?: string; limit?: number } = {},
): Promise<NewsImpactRow[]> {
  const symbols = (opts.symbols ?? []).map((s) => s.toUpperCase());
  const where = [opts.since ? "judged_at >= ?" : "1 = 1"];
  const bind: unknown[] = opts.since ? [opts.since] : [];
  if (symbols.length) {
    where.push(`symbol in (${symbols.map(() => "?").join(",")})`);
    bind.push(...symbols);
  }
  const r = (await d1
    .prepare(
      `select id, item_id, symbol, exchange, relation, direction, size, sector_only, why_en, why_bn, weight, judged_at from news_impact where ${where.join(" and ")} order by judged_at desc, weight desc limit ?`,
    )
    .bind(...bind, opts.limit ?? 500)
    .all()) as { results: Raw[] };
  return r.results.map(shape);
}
