-- What `rebuild` and `buildPairs` read besides trades and Kite holdings (same shapes as api/drizzle/holdings.ts,
-- and the Fidelity tables of the Python store). Lots and sales are never stored: they are rebuilt on every read.
create table if not exists corporate_actions (
  symbol text not null, ex_date text not null, kind text not null, isin text,
  numerator real not null, denominator real not null, subject text not null default '',
  source text not null default 'nse',
  primary key (symbol, ex_date, kind)
);
create table if not exists action_terms (
  symbol text not null, ex_date text not null, kind text not null,
  new_isin text, new_symbol text, cost_fraction real, price real,
  primary key (symbol, ex_date, kind)
);
create table if not exists trade_tags (
  trade_key text primary key, placed_by text, basket text, how text
);
create table if not exists fidelity_holdings (
  as_of text not null, symbol text not null, isin text, quantity real, cost_basis_inr real,
  value_inr real, price_usd real,
  primary key (as_of, symbol)
);
create table if not exists fidelity_lots (
  as_of text not null, symbol text not null, isin text, acquired_on text not null, quantity real,
  cost_basis_inr real not null, cost_per_share_inr real, value_inr real, gain_inr real,
  sale_available text, grant_date text, term text,
  primary key (as_of, symbol, acquired_on, cost_basis_inr)
);
