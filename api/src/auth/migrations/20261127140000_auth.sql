create table if not exists auth_links (
  hash text primary key, person text not null, next text not null, expires_at integer not null
);
create table if not exists auth_limits (
  key text primary key, n integer not null, until integer not null
);
