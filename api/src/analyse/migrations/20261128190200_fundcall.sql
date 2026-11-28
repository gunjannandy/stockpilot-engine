-- One fund Analyse call per fund and day. Public data only: no holding, SIP or tax column.
create table if not exists fund_analyse_calls (
  key text primary key, fund text not null, day text not null, call text not null, chance_pct real not null,
  source text not null, summary_en text, summary_bn text, reasons text not null, risks text not null, model text, note text,
  stored_at text not null
);
create index if not exists fund_analyse_calls_fund on fund_analyse_calls (fund, day);
