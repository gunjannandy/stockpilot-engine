create table if not exists money_budgets (month text primary key, amount_inr real not null, updated_at text not null);
create table if not exists money_mix (asset_class text primary key, share real not null, updated_at text not null);
