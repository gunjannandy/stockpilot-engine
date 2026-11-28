create table if not exists feedback (
  id text primary key,
  text text not null,
  understanding text,
  status text not null default 'received',
  ticket integer,
  stale_ticket integer,
  created_at text not null,
  reviewed_at text,
  updated_at text not null
);
create index if not exists feedback_created on feedback (created_at);
