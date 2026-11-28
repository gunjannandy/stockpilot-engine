-- The `market` dataset's table: one row a day of market health (the publish door stages its rows in dataset_rows).
create table if not exists market_health (
  id text primary key, day text not null, nifty_close real, nifty_trend_pct real, nifty_trend text, breadth_pct real,
  breadth_n integer not null, median_pe real, value_band text, sentences_json text not null
);
