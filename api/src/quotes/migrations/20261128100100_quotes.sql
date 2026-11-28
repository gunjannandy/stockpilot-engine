-- The newest near-live price per symbol, written by the quotes duty and read from here within an age limit.
create table if not exists quote_cache (
  symbol text primary key, price real not null, prev_close real, at text not null, at_ms integer not null
);
-- Symbols people asked about lately: the only ones the duty refreshes.
create table if not exists quote_watch (symbol text primary key, exchange text not null default 'NSE', asked_ms integer not null);
