create table if not exists backup_reports (
  id integer primary key autoincrement,
  kind text not null, at text not null, ok integer not null, tables text not null, detail text not null
);
create index if not exists backup_reports_kind_at on backup_reports (kind, at);
