-- The calendar dataset's table (every dataset has one; the publish door stages its rows in dataset_rows).
create table if not exists calendar (
  id text primary key, kind text not null, date text not null, reason text, symbol text,
  old_shares integer, new_shares integer, new_symbol text
);
