create table if not exists secret_expiry (
  name text primary key, expires_on text, note text, notified_at text
);
