create table if not exists usage_counts (
  day text not null, screen text not null, button text not null, n integer not null,
  primary key (day, screen, button)
);
