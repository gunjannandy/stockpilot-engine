create table if not exists monitor_usage (
  day text not null, metric text not null, value real not null, at text not null,
  primary key (day, metric)
);
