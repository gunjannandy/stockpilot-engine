-- The funds dataset's table (every dataset has one; the publish door stages its rows in dataset_rows).
create table if not exists funds (
  id text primary key, code integer not null, name text not null, amc text, category text,
  nav real, nav_date text, ter real, ter_regular real, aum_cr real,
  r1 real, r3 real, r5 real, cat_r1 real, cat_r3 real, cat_r5 real, category_n integer not null,
  max_fall real, roll_min real, roll_median real, roll_max real, roll_loss_share real, navs_json text not null
);
