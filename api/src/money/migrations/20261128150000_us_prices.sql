-- Daily closes of US-listed shares held as RSUs (public market data, written by the usprices Job).
create table if not exists us_prices (
  symbol text not null,
  date text not null,
  close real not null,
  primary key (symbol, date)
);
