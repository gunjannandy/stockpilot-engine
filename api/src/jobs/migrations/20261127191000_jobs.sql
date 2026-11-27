create table if not exists job_runs (
  key text primary key, kind text not null, subject text not null, day text not null,
  run_id text, status text not null, range_from text not null, range_to text not null,
  attempts integer not null default 0, queued_at text, dispatched_at text,
  dispatch_count integer not null default 0, started_at text, finished_at text,
  duration_ms integer, result text, error text, retry_at text
);
create index if not exists job_runs_kind_finished on job_runs (kind, finished_at);
create table if not exists job_locks (kind text primary key, run_id text not null, expires_at text not null);
create table if not exists job_pauses (kind text primary key, paused_at text not null);
create table if not exists model_usage (
  day text not null, kind text not null, used integer not null, primary key (day, kind)
);
create table if not exists model_cache (
  key text primary key, kind text not null, day text not null, answer text not null, at text not null
);
