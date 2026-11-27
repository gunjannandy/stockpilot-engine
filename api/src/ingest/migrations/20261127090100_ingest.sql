create table if not exists jobs (
  id text primary key, kind text not null, status text not null, result text, error text,
  started_at text not null, finished_at text
);
create index if not exists jobs_kind_started on jobs (kind, started_at);
create table if not exists write_budget (
  day text not null, dataset text not null, writes integer not null, primary key (day, dataset)
);
