-- Calls: append-only (a new call is a new row, id = exchange:symbol:day:horizon; nothing updates or deletes one).
-- call_scores is written by the scoring Job (record) once a call's window has ended; it is a second table so a call row never changes.
create table if not exists calls (
  id text primary key, symbol text not null, exchange text not null, made_on text not null, verdict text not null,
  chance real, horizon_days integer not null, base_cases integer not null, base_rate real, sell_line real not null,
  buy_line real not null, could_rise_to real, would_buy_at real, sell_at_once_at real, limited integer not null,
  sentences_json text not null, similar_n integer not null, similar_beat integer not null, model_version text not null
);
create index if not exists calls_symbol on calls (symbol, made_on);
create index if not exists calls_day on calls (made_on);
create table if not exists call_scores (
  call_id text primary key, beat integer not null, scored_on text not null
);
-- The `calls_runs` dataset's table: one summary row per nightly forecast run.
create table if not exists calls_runs (
  id text primary key, day text not null, written integer not null, held_back integer not null
);
-- The `screen` dataset's table: the screen publishes one file per run, so only its row shape lives here (previews seed it).
create table if not exists screen_runs (
  symbol text not null, exchange text not null, industry text not null, quality real, value real, momentum real, risk real,
  score real, rank integer, excluded text
);
