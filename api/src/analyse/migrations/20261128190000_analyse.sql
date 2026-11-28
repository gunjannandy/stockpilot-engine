-- One Analyse call per stock and day (a rerun replaces it). Public data only: no holding, tax or account column.
create table if not exists analyse_calls (
  key text primary key, symbol text not null, day text not null, call text not null, chance_pct real not null,
  source text not null, summary_en text, summary_bn text, reasons text not null, risks text not null, model text, note text,
  stored_at text not null
);
create index if not exists analyse_calls_symbol on analyse_calls (symbol, day);
