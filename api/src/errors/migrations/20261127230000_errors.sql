create table if not exists browser_errors (
  id text primary key,
  at text not null,
  message text not null,
  stack text,
  pane text,
  url text,
  version text,
  user_agent text
);
create index if not exists browser_errors_at on browser_errors (at);
