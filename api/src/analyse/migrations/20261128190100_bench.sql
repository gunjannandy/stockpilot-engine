-- Bench reports: one row per scored run, newest wins. The state row remembers whether the bench itself paused releases.
create table if not exists bench_reports (
  at text primary key, fingerprint text not null, model text not null, red text not null, body text not null
);
create table if not exists bench_state (key text primary key, value text not null);
