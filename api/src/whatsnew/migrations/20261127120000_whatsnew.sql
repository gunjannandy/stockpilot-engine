create table if not exists whatsnew_seen (person text not null, pr integer not null, at text not null, primary key (person, pr));
