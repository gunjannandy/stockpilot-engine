-- The fund_holdings dataset's table (every dataset has one; the publish door stages its rows in dataset_rows).
create table if not exists fund_holdings (
  id text primary key, name text not null, amc text, as_of text, holdings_json text not null
);
