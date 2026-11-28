-- Record: call_scores (made by the calls migration) is filled by the scoring Job, one insert-only row per scored call,
-- now with the three returns over the call's window (stock, Nifty, equal-weight watchlist) that "adding value" averages.
-- Nothing here updates or deletes a row.
alter table call_scores add column stock_ret real;
alter table call_scores add column nifty_ret real;
alter table call_scores add column equal_ret real;
-- The `record_runs` dataset's table: one summary row per nightly scoring run.
create table if not exists record_runs (
  id text primary key, day text not null, scored integer not null
);
