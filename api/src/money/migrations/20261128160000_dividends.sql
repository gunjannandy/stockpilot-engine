-- Cash dividends per share by ex-date for stocks held (public market data, written by the dividends Job).
create table if not exists dividends (
  symbol text not null,
  ex_date text not null,
  per_share real not null,
  primary key (symbol, ex_date)
);
-- The `dividends` dataset's table: one summary row per daily run.
create table if not exists dividends_runs (
  id text primary key, day text not null, symbols integer not null, rows integer not null
);
