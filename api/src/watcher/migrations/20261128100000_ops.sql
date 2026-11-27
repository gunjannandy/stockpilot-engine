create table if not exists watcher_alerts (subject text primary key, issue integer, opened_at text not null, closed_at text);
create table if not exists promise_results (day text not null, promise text not null, ok integer not null, detail text not null, at text not null, primary key (day, promise));
create table if not exists dep_checks (dep text primary key, ok integer not null, detail text not null, fallback text not null, at text not null);
create table if not exists rollbacks (version text primary key, at text not null, detail text not null, issue integer);
