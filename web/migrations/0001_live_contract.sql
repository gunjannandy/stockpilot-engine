-- v2 live data contract, migration 0001 (ticket T0). Matches schemas/live-contract.json.
-- Append new tables in a new migration file; never edit this one after it has run on D1.

create table calls (
  symbol text not null,
  exchange text not null,
  call text not null,
  route text not null,
  chance_3m real not null,
  chance_6m real not null,
  confidence text not null,
  low_1m real not null,
  likely_1m real not null,
  high_1m real not null,
  low_3m real not null,
  likely_3m real not null,
  high_3m real not null,
  low_6m real not null,
  likely_6m real not null,
  high_6m real not null,
  model text not null,
  form text not null,
  as_of text not null,
  written_at text not null,
  out_of_date integer not null,
  news_buy integer not null,
  primary key (symbol, exchange)
);
create index idx_calls_written_at on calls (written_at);

create table lists (
  list_name text not null,
  symbol text not null,
  exchange text not null,
  rank integer not null,
  reason text not null,
  reason_bn text,
  since text not null,
  primary key (list_name, symbol, exchange)
);

create table jobs (
  id text not null,
  kind text not null,
  payload text not null,
  asked_by text not null,
  status text not null,
  result text,
  error text,
  error_bn text,
  created_at text not null,
  started_at text,
  finished_at text,
  primary key (id)
);
create index idx_jobs_status_created_at on jobs (status, created_at);

create table job_lines (
  job_id text not null,
  seq integer not null,
  at text not null,
  state text not null,
  text text not null,
  text_bn text,
  primary key (job_id, seq)
);

create table changes (
  id text not null,
  person text not null,
  symbol text not null,
  kind text not null,
  old_value text,
  new_value text,
  reason text not null,
  reason_bn text,
  at text not null,
  seen_at text,
  primary key (id)
);
create index idx_changes_person_seen_at on changes (person, seen_at);

create table feedback (
  id text not null,
  person text not null,
  text text not null,
  status text not null,
  created_at text not null,
  primary key (id)
);

create table asks (
  id text not null,
  feedback_id text not null,
  original text not null,
  line_en text not null,
  line_bn text not null,
  tag text not null,
  size text not null,
  plan text not null,
  route text not null,
  status text not null,
  not_meant integer not null,
  issue_number integer,
  updated_at text not null,
  primary key (id)
);

create table news_items (
  id text not null,
  link text not null,
  title text not null,
  source text not null,
  published_at text not null,
  group_id text not null,
  source_count integer not null,
  sector text,
  market_wide integer not null,
  direction text not null,
  impact integer not null,
  line_en text,
  line_bn text,
  tagged_at text,
  primary key (id)
);
create index idx_news_items_published_at on news_items (published_at);
create index idx_news_items_group_id on news_items (group_id);

create table news_tags (
  item_id text not null,
  symbol text not null,
  exchange text not null,
  relation text not null,
  direction text not null,
  size text not null,
  changes_call integer not null,
  primary key (item_id, symbol, exchange)
);
create index idx_news_tags_symbol on news_tags (symbol);

create table news_rank (
  item_id text not null,
  closeness text not null,
  score real not null,
  tier text not null,
  ranked_at text not null,
  primary key (item_id)
);

create table quotes (
  symbol text not null,
  exchange text not null,
  price real not null,
  prev_close real not null,
  as_of text not null,
  source text not null,
  primary key (symbol, exchange)
);

create table write_budget (
  day text not null,
  writes integer not null,
  warn_at integer not null,
  stop_at integer not null,
  updated_at text not null,
  primary key (day)
);
