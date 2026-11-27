// The public tables the ingest Worker may write. Copied from schemas/live-contract.json
// (tables whose writer is "ingest"); web/test/ingest.test.mjs fails if the two drift apart.
// `cost` = rows D1 counts per written row: 1 plus one per index.
export const PUBLIC_TABLES = {
  news_items: { columns: ["id","link","title","source","published_at","group_id","source_count","sector","market_wide","direction","impact","line_en","line_bn","tagged_at"], cost: 3 },
  news_tags: { columns: ["item_id","symbol","exchange","relation","direction","size","changes_call"], cost: 2 },
  quotes: { columns: ["symbol","exchange","price","prev_close","as_of","source"], cost: 1 },
};
export const WARN_AT = 60000;
export const STOP_AT = 85000;
