-- News items (ranked, links only) and the append-only impact table every consumer reads (only ever inserted).
create table if not exists news_items (
  id text primary key, link text not null, title text not null, source text not null, published_at text not null,
  source_count integer not null, weight integer not null
);
create table if not exists news_impact (
  id text primary key, item_id text not null, symbol text not null, exchange text not null, relation text not null,
  direction text, size text not null, sector_only integer not null, why_en text not null, why_bn text not null,
  weight integer not null, judged_at text not null
);
create table if not exists news_judged (item_id text primary key, at text not null);
create index if not exists news_impact_symbol on news_impact (symbol, judged_at);
create index if not exists news_impact_item on news_impact (item_id);
