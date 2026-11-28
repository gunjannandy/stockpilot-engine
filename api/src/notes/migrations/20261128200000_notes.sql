-- One post-mortem per missed call (public data only), and the nightly note the scheduled task writes back.
create table if not exists postmortems (
  call_key text primary key, symbol text not null, day text not null, call text not null, excess_pct real not null,
  cause text not null, why_en text not null, why_bn text not null, evidence text not null, source text not null,
  model text, stored_at text not null
);
create index if not exists postmortems_stored on postmortems (stored_at);
create table if not exists nightly_notes (day text primary key, text_en text not null, text_bn text not null, stored_at text not null);
