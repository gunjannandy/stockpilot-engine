-- Prototypes waiting for the owner's word. The hourly Apps Script run lists the ones not yet announced.
create table if not exists prototypes_waiting (
  id text primary key, title text not null, link text not null, waiting_since text not null, announced_at text
);
