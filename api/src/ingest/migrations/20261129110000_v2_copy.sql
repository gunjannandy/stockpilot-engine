-- Tables only the one-time v2 copy fills (contract/src/migrate): the record's v2 rows, kept whole as JSON text.
create table if not exists archived_days (day text primary key, payload text not null);
create table if not exists long_term_marks (symbol text primary key, marked_at text not null, payload text not null);
create table if not exists smallcase_orders (order_key text primary key, placed_at text not null, payload text not null);
