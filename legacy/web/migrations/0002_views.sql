-- T29: the private screens' documents. Matches schemas/live-contract.json, table `views`.
create table views (
  name text not null,
  doc text not null,
  as_of text not null,
  written_at text not null,
  primary key (name)
);
