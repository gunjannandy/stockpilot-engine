-- USD/INR daily reference rates for pricing foreign lots. Filled from a free public feed; never hand-entered.
create table if not exists fx_rates (
  day text primary key,
  usd_inr real not null,
  source text not null default 'frankfurter'
);
