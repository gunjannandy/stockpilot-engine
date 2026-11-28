-- The notes table moved here from health; already present where health's migration ran.
create table if not exists whatsnew (pr integer primary key, en text not null, bn text not null, at text not null);
