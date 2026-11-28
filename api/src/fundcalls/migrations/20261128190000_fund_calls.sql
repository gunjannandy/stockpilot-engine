-- The fund_calls dataset's table (the publish door stages its rows in dataset_rows).
create table if not exists fund_calls (
  id text primary key, kind text not null, name text not null, category text, call text,
  rank integer, "of" integer, quartile integer not null, chance real, cases integer, periods integer,
  avg_excess real, reasons text not null, caveat text not null, as_of text not null
);
