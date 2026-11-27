create table if not exists check_results (check_id text primary key, ok integer not null, at text not null, detail text not null);
create table if not exists deploys (version text primary key, first_seen_at text not null);
