create table if not exists heartbeats (
  part text primary key, version text not null, at text not null, ok integer not null,
  error text, next_expected_by text, last_success text
);
create table if not exists whatsnew (pr integer primary key, en text not null, bn text not null, at text not null);
