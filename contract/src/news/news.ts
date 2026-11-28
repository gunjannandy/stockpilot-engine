import { z } from "zod";

/** Source weights: a filing outweighs a wire, a wire outweighs a blog. */
export const NewsWeight = z.union([z.literal(1), z.literal(2), z.literal(3)]);

/** One ranked news item, a row of the `news_items` dataset (links and titles only). */
export const NewsItemRow = z.object({
  id: z.string().min(1),
  link: z.string().min(1),
  title: z.string().min(1),
  source: z.string().min(1),
  published_at: z.string(),
  source_count: z.number().int().min(1),
  weight: NewsWeight,
});
export type NewsItemRow = z.infer<typeof NewsItemRow>;

export const NewsRelation = z.enum(["self", "rival", "supplier", "customer", "sector"]);
export const NewsDirection = z.enum(["good", "bad", "mixed"]);

/** One impact row: one news item's effect on one stock. The table is append-only. A sector-only link has no
 * direction and shows as a grey "sector news" mark. */
export const NewsImpactRow = z.object({
  id: z.string().min(1),
  item_id: z.string().min(1),
  symbol: z.string().min(1),
  exchange: z.enum(["NSE", "BSE"]),
  relation: NewsRelation,
  direction: NewsDirection.nullable(),
  size: z.enum(["small", "medium", "large"]),
  sector_only: z.boolean(),
  why_en: z.string(),
  why_bn: z.string(),
  weight: NewsWeight,
  judged_at: z.string(),
});
export type NewsImpactRow = z.infer<typeof NewsImpactRow>;

/** The first reason an impact row is refused, or null. */
export function newsImpactRowCheck(r: NewsImpactRow): string | null {
  if (r.sector_only && r.direction !== null) return "a sector-only link carries no direction";
  if (!r.sector_only && r.relation === "sector") return "a sector relation is sector-only";
  if (r.id !== `${r.item_id}:${r.symbol}`) return "id must be item_id:symbol";
  if (!r.sector_only && !/[ঀ-৿]/.test(r.why_bn)) return "why has no Bengali";
  return null;
}

/** `judged_ids`: every item the model answered for, with or without a stock, so none is judged twice. */
export const NewsImpactRequest = z.object({
  rows: z.array(NewsImpactRow).max(500),
  judged_ids: z.array(z.string().min(1)).max(500).default([]),
});

/** What a card shows: an item with the stocks it affects. */
export const NewsCard = NewsItemRow.extend({ impacts: z.array(NewsImpactRow) });
export type NewsCard = z.infer<typeof NewsCard>;
export const NewsResponse = z.object({ items: z.array(NewsCard) });
export type NewsResponse = z.infer<typeof NewsResponse>;

/** The seven consumers that read only the impact table (decisions §7). */
export const NEWS_CONSUMERS = [
  "refresh triggers",
  "forecast levels and bands",
  "change marks",
  "in today's news",
  "near-live picks",
  "exposure",
  "nightly note",
] as const;
