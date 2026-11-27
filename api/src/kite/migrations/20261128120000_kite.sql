-- Raw holdings, trades and what each Kite sync read (same shapes as api/drizzle/holdings.ts).
create table if not exists holdings (
  account text not null, source text not null, snapshot_at text not null, kind text not null,
  symbol text not null, isin text, quantity real not null, avg_price real not null,
  primary key (account, source, snapshot_at, kind, symbol, isin)
);
create index if not exists holdings_snapshot on holdings (account, snapshot_at);
create table if not exists trades (
  trade_key text primary key, account text not null, source text not null, source_ref text not null,
  kind text not null, symbol text not null, isin text, side text not null, trade_date text not null,
  quantity real not null, price real, currency text not null default 'INR', status text not null default 'confirmed'
);
create index if not exists trades_account_date on trades (account, trade_date);
create index if not exists trades_isin on trades (isin);
create table if not exists kite_syncs (
  account text not null, source text not null default 'kite', fetched_at text not null,
  trades text, positions text, margins text, gtts text, changes integer,
  primary key (account, fetched_at)
);
