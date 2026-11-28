-- Every day's prices for every stock, appended by the history Jobs (one row a stock a day).
create table if not exists stock_history (
  symbol text not null, exchange text not null, date text not null,
  open real, high real, low real, close real not null, prev_close real, volume real,
  primary key (symbol, exchange, date)
) without rowid;
-- The `universe` dataset's table (every dataset has one; the publish door stages its rows in dataset_rows).
create table if not exists universe (
  id text primary key, symbol text not null, exchange text not null, segment text not null,
  name text not null, isin text not null, aliases text not null, status text not null
);
-- The `history` dataset's table: one summary row per daily run.
create table if not exists history_runs (
  id text primary key, day text not null, stocks integer not null, held_back integer not null
);
