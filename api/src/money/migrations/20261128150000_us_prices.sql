-- Daily closes of US-listed shares held as RSUs (public market data, written by the usprices Job).
create table if not exists us_prices (
  symbol text not null,
  date text not null,
  close real not null,
  primary key (symbol, date)
);
-- The `usprices` dataset's table: one summary row per daily run.
create table if not exists usprices_runs (
  id text primary key, day text not null, symbols integer not null, rows integer not null, held_back integer not null
);
