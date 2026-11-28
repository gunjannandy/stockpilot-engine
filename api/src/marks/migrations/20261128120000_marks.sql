create table if not exists mark_seen (dataset text not null, row_key text not null, run_id text not null, seen_at text not null, by_person text, primary key (dataset, row_key, run_id));
