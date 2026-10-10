-- Personal finance schema (Supabase / Postgres)
-- Conventions:
--   amount  = signed effect on the account balance, fees included. Negative = money out.
--   Totals only over status = 'booked' and type <> 'ignore'. Use the views, not the raw table.

-- ---------- enums ----------
create type txn_type as enum ('expense', 'income', 'transfer', 'cash', 'fee', 'refund', 'ignore');
create type txn_status as enum ('booked', 'pending', 'reverted');
create type category_source as enum ('rule', 'ai', 'manual');

-- ---------- accounts ----------
create table accounts (
  id            text primary key,              -- e.g. 'sparkasse_giro', 'revolut_eur'
  name          text not null,
  institution   text not null,
  iban          text unique,                   -- full IBAN, used to detect own-account transfers
  currency      char(3) not null default 'EUR',
  source_format text,                          -- 'sparkasse_csv_camt_v2' | 'revolut_csv' | null for untracked
  is_tracked    boolean not null default true, -- false = own account we do not import (only used for transfer detection)
  created_at    timestamptz not null default now()
);
comment on table accounts is 'Own bank accounts. Untracked ones exist only so transfers to/from them are typed as transfer.';

-- ---------- categories ----------
create table categories (
  id          serial primary key,
  name        text not null unique,
  parent_id   int references categories(id),
  kind        text not null check (kind in ('spend', 'income', 'transfer', 'other')),
  is_essential boolean,
  color       text
);

-- ---------- imports ----------
create table imports (
  id             bigserial primary key,
  account_id     text not null references accounts(id),
  file_name      text not null,
  file_sha256    text not null,
  rows_in_file   int not null,
  rows_inserted  int not null,
  rows_skipped   int not null,
  pending_replaced int not null default 0,
  date_from      date,
  date_to        date,
  imported_at    timestamptz not null default now()
);

-- ---------- transactions ----------
create table transactions (
  id                bigserial primary key,
  account_id        text not null references accounts(id),
  import_id         bigint references imports(id),
  status            txn_status not null,
  type              txn_type not null,

  transacted_at     timestamp,                 -- when it actually happened (card timestamp / Revolut Started Date)
  booking_date      date not null,             -- when the bank booked it
  value_date        date,

  amount            numeric(12,2) not null,    -- signed, account currency, fees included
  fee               numeric(12,2) not null default 0, -- informational: part of amount that was a fee (positive)
  currency          char(3) not null,
  original_amount   numeric(14,2),
  original_currency char(3),
  fx_rate           numeric(16,8),
  balance_after     numeric(12,2),

  source_type       text not null,             -- Sparkasse Buchungstext / Revolut Type
  merchant          text,
  city              text,
  country           char(2),
  counterparty_raw  text,
  counterparty_iban text,
  description_raw   text,
  card_ref          text,

  category_id       int references categories(id),
  category_source   category_source,
  transfer_group    uuid,                      -- same value on both sides of an internal transfer
  needs_review      boolean not null default false,
  notes             text,

  creditor_id       text,                      -- SEPA creditor ID (recurring detection)
  mandate_ref       text,
  end_to_end_ref    text,                      -- not unique, never use as key

  dedup_hash        text not null unique,
  raw               jsonb not null,            -- original CSV row, untouched
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);
comment on column transactions.amount is 'Signed balance effect incl. fees. Revolut: Amount - Fee. Sparkasse: Betrag.';
comment on column transactions.type is 'expense|income|transfer|cash|fee|refund|ignore. Transfers are between own accounts and excluded from spend/income.';
comment on column transactions.dedup_hash is 'sha256 of stable source fields. Pending rows are deleted and reinserted on each import.';

create index on transactions (account_id, booking_date);
create index on transactions (transacted_at);
create index on transactions (category_id);
create index on transactions (merchant);
create index on transactions (type, status);

-- ---------- merchant rules ----------
create table merchant_rules (
  id              serial primary key,
  priority        int not null default 100,    -- lower runs first, first match wins
  account_id      text references accounts(id),-- null = all accounts
  match_field     text not null check (match_field in ('merchant', 'counterparty_raw', 'description_raw', 'source_type')),
  pattern         text not null,               -- case-insensitive regex
  set_merchant    text,
  set_category_id int references categories(id),
  set_type        txn_type,
  note            text,
  created_at      timestamptz not null default now()
);

-- ---------- updated_at trigger ----------
create function set_updated_at() returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end $$;
create trigger trg_transactions_updated before update on transactions
  for each row execute function set_updated_at();

-- ---------- views ----------
create view v_transactions as
select t.*,
       a.name  as account_name,
       c.name  as category,
       p.name  as parent_category,
       date_trunc('month', coalesce(t.transacted_at, t.booking_date))::date as month
from transactions t
join accounts a on a.id = t.account_id
left join categories c on c.id = t.category_id
left join categories p on p.id = c.parent_id
where t.status = 'booked' and t.type <> 'ignore';
comment on view v_transactions is 'Booked, non-ignored transactions with names resolved. Default source for analysis.';

create view v_spend as
select *, -amount as spend
from v_transactions
where type in ('expense', 'cash', 'fee', 'refund');
comment on view v_spend is 'Spending only. spend is positive for outflows, negative for refunds. Transfers excluded.';

create view v_monthly as
select month,
       sum(case when type = 'income' then amount else 0 end)                        as income,
       sum(case when type in ('expense','cash','fee','refund') then -amount else 0 end) as spend,
       sum(case when type in ('income','expense','cash','fee','refund') then amount else 0 end) as net
from v_transactions
group by month
order by month;

create view v_review_queue as
select * from transactions
where status = 'booked' and type <> 'ignore'
  and (category_id is null or needs_review);

create view v_category_monthly as
select month,
       coalesce(category, 'Uncategorized') as category,
       parent_category,
       sum(spend)  as spend,
       count(*)    as txn_count
from v_spend
group by month, coalesce(category, 'Uncategorized'), parent_category
order by month, spend desc;
comment on view v_category_monthly is 'Spend per category per month. Source for trends and month over month comparisons.';

create view v_recurring as
with s as (
  select coalesce(merchant, counterparty_raw) as merchant,
         category,
         coalesce(transacted_at::date, booking_date) as d,
         spend
  from v_spend
  where type = 'expense' and spend > 0 and coalesce(merchant, counterparty_raw) is not null
),
g as (
  select *, d - lag(d) over (partition by merchant order by d) as gap_days
  from s
),
agg as (
  select merchant,
         max(category)                                          as category,
         count(*)                                               as charges,
         round(avg(spend), 2)                                   as avg_amount,
         (array_agg(spend order by d desc))[1]                  as last_amount,
         round((stddev_pop(spend) / nullif(avg(spend), 0))::numeric, 3) as amount_cv,
         percentile_cont(0.5) within group (order by gap_days)  as median_gap_days,
         min(d) as first_charge,
         max(d) as last_charge
  from g
  group by merchant
),
c as (
  select *,
         case when median_gap_days between 25 and 35   then 'monthly'
              when median_gap_days between 6 and 8     then 'weekly'
              when median_gap_days between 350 and 380 then 'yearly'
              else 'irregular' end as cadence
  from agg
)
select merchant, category, cadence, charges, avg_amount, last_amount, amount_cv,
       median_gap_days, first_charge, last_charge,
       (last_charge + make_interval(days => median_gap_days::int))::date as next_expected,
       last_charge >= current_date - (median_gap_days * 1.5)::int      as is_active,
       case cadence when 'monthly' then last_amount * 12
                    when 'weekly'  then last_amount * 52
                    when 'yearly'  then last_amount end                as yearly_cost
from c
where cadence <> 'irregular'
  and amount_cv <= 0.2
  and charges >= case when cadence = 'yearly' then 2 else 3 end;
comment on view v_recurring is 'Detected subscriptions / recurring charges: same merchant, stable amount (cv <= 0.2), regular interval.';

-- ---------- security ----------
alter table accounts       enable row level security;
alter table categories     enable row level security;
alter table imports        enable row level security;
alter table transactions   enable row level security;
alter table merchant_rules enable row level security;
alter view v_transactions     set (security_invoker = true);
alter view v_spend            set (security_invoker = true);
alter view v_monthly          set (security_invoker = true);
alter view v_review_queue     set (security_invoker = true);
alter view v_category_monthly set (security_invoker = true);
alter view v_recurring        set (security_invoker = true);

revoke all on all tables    in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;
revoke all on all functions in schema public from anon, authenticated;
grant usage on schema public to service_role;
grant all on all tables    in schema public to service_role;
grant all on all sequences in schema public to service_role;

-- ---------- seed: categories ----------
insert into categories (name, kind, is_essential) values
  ('Groceries', 'spend', true),
  ('Restaurants & Cafes', 'spend', false),
  ('Food Delivery', 'spend', false),
  ('Public Transport', 'spend', true),
  ('Taxi & Rideshare', 'spend', false),
  ('Travel', 'spend', false),
  ('Shopping', 'spend', false),
  ('Subscriptions & Software', 'spend', false),
  ('Phone & Internet', 'spend', true),
  ('Housing & Utilities', 'spend', true),
  ('Health & Personal Care', 'spend', true),
  ('Entertainment & Events', 'spend', false),
  ('Education', 'spend', true),
  ('Gifts & Friends', 'spend', false),
  ('Cash', 'spend', null),
  ('Fees', 'spend', null),
  ('Salary', 'income', null),
  ('Freelance', 'income', null),
  ('Family', 'income', null),
  ('Cashback & Rewards', 'income', null),
  ('Other Income', 'income', null),
  ('Internal Transfer', 'transfer', null),
  ('Uncategorized', 'other', null);
