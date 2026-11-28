-- Worth following lists (the lists Job's dataset), the watchlist and Not now. A star and a Not now are direct row
-- writes in the Worker: no Job row. A star holds a stock (symbol) or a fund (ISIN).
create table if not exists list_rows (
  id text primary key, list text not null, symbol text not null, exchange text not null, position integer not null,
  reasons_json text not null, updated_at text not null
);
create table if not exists watchlist (
  id text primary key, kind text not null, name text, added_at text not null
);
create table if not exists not_now (
  symbol text primary key, until text not null, created_at text not null
);
