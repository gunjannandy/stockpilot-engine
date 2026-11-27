create table if not exists runs (
  dataset text not null, run_id text not null, status text not null,
  source text not null, fetched_at text not null, as_of text not null,
  accepted integer not null default 0, held integer not null default 0, refused integer not null default 0,
  started_at text not null, finished_at text, error text,
  primary key (dataset, run_id)
);
create table if not exists dataset_rows (
  dataset text not null, run_id text not null, seq integer not null, body text not null,
  primary key (dataset, run_id, seq)
) without rowid;
create table if not exists held_rows (
  dataset text not null, run_id text not null, seq integer not null, reason text not null, body text not null,
  primary key (dataset, run_id, seq)
);
create table if not exists pointers (
  dataset text primary key, run_id text not null, previous_run_id text, as_of text not null,
  published_at text not null, rows integer not null, file text, summary text not null
);
