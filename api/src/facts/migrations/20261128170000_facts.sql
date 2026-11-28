-- The facts dataset's table (every dataset has one; the publish door stages its rows in dataset_rows).
create table if not exists facts (
  id text primary key, symbol text not null, exchange text not null, name text, sector text, as_of text not null,
  pe real, pe_sector real, pb real, dividend_yield_pct real, market_cap_cr real,
  sales_growth_yoy_pct real, profit_growth_yoy_pct real, roe_pct real, roce_pct real, debt_to_equity real,
  promoter_pct real, pledge_pct real, sentences_json text not null, figures_json text not null, not_available text
);
