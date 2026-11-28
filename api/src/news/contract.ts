// The contract every consumer of news obeys: read impact through `readImpact`, never the raw sector tag.
import type { NEWS_CONSUMERS } from "@stockpilot/contract";

/** Where each named consumer lives (repo-relative). A consumer whose area is not built yet has no files. */
export const CONSUMER_FILES: Record<(typeof NEWS_CONSUMERS)[number], string[]> = {
  "refresh triggers": [],
  "forecast levels and bands": [],
  "change marks": [],
  "in today's news": ["api/src/news/routes.ts"],
  "near-live picks": [],
  exposure: [],
  "nightly note": [],
};

/** Ways a consumer may touch the raw tag: the old tag tables or a sector field of a news item. */
const RAW = [
  /\bnews_tags\b/,
  /\bnews_items\b[^;]*\bsector\b/s,
  /\bitem\.sector\b/,
  /\.sector_tag\b/,
  /\bsectorTag\b/,
];

/** Reasons this source breaks the contract (empty when it does not). */
export function rawTagReads(source: string): string[] {
  return RAW.filter((re) => re.test(source)).map((re) => `reads the raw sector tag (${re.source})`);
}

export const readsImpactTable = (source: string): boolean =>
  /\breadImpact\b/.test(source) || /\bnews_impact\b/.test(source);
