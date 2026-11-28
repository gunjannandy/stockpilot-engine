-- The documents dataset's table: trades the readers found in the owner's files, keyed by trade key.
create table if not exists document_trades (
  trade_key text primary key, account text not null, source text not null, source_ref text not null,
  kind text not null, symbol text not null, isin text, side text not null, trade_date text not null,
  quantity real not null, price real
);
