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
create index categories_parent_id_idx on categories(parent_id);
alter table categories add constraint categories_not_self_parent check (parent_id is null or parent_id <> id);

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

-- ---------- subscriptions ----------
create table subscriptions (
  id             bigserial primary key,
  name           text not null unique,
  merchant_match text not null,
  category_id    int references categories(id),
  cadence        text not null check (cadence in ('weekly', 'monthly', 'quarterly', 'yearly')),
  amount         numeric(12,2) not null default 0 check (amount >= 0),
  currency       char(3) not null default 'EUR',
  status         text not null default 'active' check (status in ('active', 'paused', 'cancelled')),
  notes          text,
  sort_order     int not null default 100,
  created_at     timestamptz not null default now()
);
comment on table subscriptions is 'User-maintained subscriptions. Membership and status are independent of transaction frequency.';

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
comment on view v_recurring is 'Detected recurring transaction patterns only; not an authoritative subscription inventory.';

-- ---------- security ----------
alter table accounts       enable row level security;
alter table categories     enable row level security;
alter table imports        enable row level security;
alter table transactions   enable row level security;
alter table merchant_rules enable row level security;
alter table subscriptions  enable row level security;
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
  ('Food', 'spend', false),
  ('Transport', 'spend', true),
  ('Subscriptions', 'spend', false),
  ('Housing & Utilities', 'spend', true),
  ('Health', 'spend', true),
  ('Entertainment', 'spend', false),
  ('Finance', 'spend', null),
  ('Income', 'income', null),
  ('Transfers', 'transfer', null);

insert into categories (name, parent_id, kind, is_essential)
select x.name, p.id, p.kind, x.is_essential
from (values
  ('Groceries', 'Food', true), ('Restaurants', 'Food', false),
  ('Cafe / Bakery', 'Food', false), ('Delivery', 'Food', false), ('Fast Food', 'Food', false), ('Snacks', 'Food', false),
  ('Public Transport', 'Transport', true), ('Taxi & Rideshare', 'Transport', false),
  ('Scooters & E-bikes', 'Transport', false), ('Planes & Trains', 'Transport', false),
  ('Other Transport', 'Transport', false),
  ('Shopping', 'Entertainment', false), ('Going Out', 'Entertainment', false),
  ('AI Tools', 'Subscriptions', false), ('Other Subscriptions', 'Subscriptions', false),
  ('Rent', 'Housing & Utilities', true), ('Utilities', 'Housing & Utilities', true),
  ('Internet & Phone', 'Housing & Utilities', true), ('Broadcasting Fees', 'Housing & Utilities', true),
  ('Fitness', 'Health', true), ('Weed', 'Health', false), ('Other Health', 'Health', true),
  ('Cash & Fees', 'Finance', null), ('Investments', 'Finance', null),
  ('Salary', 'Income', null), ('Freelance', 'Income', null), ('Family', 'Income', null),
  ('Cashback & Rewards', 'Income', null), ('Other Income', 'Income', null),
  ('Internal Transfer', 'Transfers', null)
) as x(name, parent_name, is_essential)
join categories p on p.name = x.parent_name;

-- ---------- seed: subscriptions ----------
insert into subscriptions (name, merchant_match, category_id, cadence, amount, status, notes, sort_order)
select x.name, x.merchant_match, c.id, x.cadence, x.amount, x.status, x.notes, x.sort_order
from (values
  ('Rent', 'Eukia Vermietungs- und Verwaltungs GmbH', 'Rent', 'monthly', 1090.00::numeric, 'active', null::text, 1),
  ('PYUR Wi-Fi', 'PYUR', 'Internet & Phone', 'monthly', 24.99::numeric, 'active', null::text, 2),
  ('Spotify', 'Spotify', 'Other Subscriptions', 'monthly', 6.99::numeric, 'active', null::text, 3),
  ('Cursor', 'CURSOR, AI POWERED IDE', 'AI Tools', 'monthly', 0.00::numeric, 'active', 'Student trial; currently billed at €0.', 4),
  ('Fitness First', 'Fitness First', 'Fitness', 'monthly', 39.80::numeric, 'paused', null::text, 5),
  ('Claude', 'ANTHROPIC', 'AI Tools', 'monthly', 21.42::numeric, 'active', null::text, 6)
) as x(name, merchant_match, category_name, cadence, amount, status, notes, sort_order)
join categories c on c.name = x.category_name
on conflict (name) do update set
  merchant_match = excluded.merchant_match,
  category_id = excluded.category_id,
  cadence = excluded.cadence,
  amount = excluded.amount,
  status = excluded.status,
  notes = excluded.notes,
  sort_order = excluded.sort_order;
-- ---------- trips ----------
create table trips (
  id          bigserial primary key,
  name        text not null,
  destination text,
  start_date  date not null,
  end_date    date not null,
  notes       text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  check (end_date >= start_date)
);
comment on table trips is 'Trips. Transactions dated within start_date..end_date belong to the trip automatically (spend types only), adjusted by trip_transactions overrides.';

create trigger trg_trips_updated before update on trips
  for each row execute function set_updated_at();

create table trip_transactions (
  trip_id        bigint not null references trips(id) on delete cascade,
  transaction_id bigint not null references transactions(id) on delete cascade,
  included       boolean not null,
  created_at     timestamptz not null default now(),
  primary key (trip_id, transaction_id)
);
create index on trip_transactions (transaction_id);

create view v_trip_transactions as
select tr.id   as trip_id,
       tr.name as trip_name,
       t.*,
       -t.amount as spend,
       coalesce(t.transacted_at::date, t.booking_date) as txn_date,
       (o.included is true) as manually_added
from trips tr
join v_transactions t
  on (
       coalesce(t.transacted_at::date, t.booking_date) between tr.start_date and tr.end_date
       and t.type in ('expense', 'cash', 'fee', 'refund')
     )
  or exists (select 1 from trip_transactions x
             where x.trip_id = tr.id and x.transaction_id = t.id and x.included)
left join trip_transactions o
  on o.trip_id = tr.id and o.transaction_id = t.id
where coalesce(o.included, true)
  and t.parent_category is distinct from 'Housing & Utilities';
comment on view v_trip_transactions is 'All transactions per trip: spend types dated within the trip range, plus manual includes, minus manual excludes. Housing & Utilities is excluded. spend is positive for outflows.';

create view v_trip_summary as
select tr.id as trip_id, tr.name, tr.destination, tr.start_date, tr.end_date, tr.notes,
       (tr.end_date - tr.start_date + 1)                           as days,
       count(v.id)                                                 as txn_count,
       coalesce(sum(v.spend), 0)                                   as total_spend,
       round(coalesce(sum(v.spend), 0) / (tr.end_date - tr.start_date + 1), 2) as avg_per_day,
       coalesce(sum(v.spend) filter (where v.type = 'cash'), 0)    as cash,
       coalesce(sum(v.spend) filter (where v.type = 'fee'), 0) + coalesce(sum(v.fee), 0) as fees
from trips tr
left join v_trip_transactions v on v.trip_id = tr.id
group by tr.id;
comment on view v_trip_summary is 'One row per trip with totals. fees = fee-type rows plus fees embedded in other rows (FX markup, ATM fees).';

alter table trips             enable row level security;
alter table trip_transactions enable row level security;
alter view v_trip_transactions set (security_invoker = true);
alter view v_trip_summary      set (security_invoker = true);
revoke all on trips, trip_transactions from anon, authenticated;
revoke all on v_trip_transactions, v_trip_summary from anon, authenticated;
revoke all on sequence trips_id_seq from anon, authenticated;
grant all on trips, trip_transactions to service_role;
grant select on v_trip_transactions, v_trip_summary to service_role;
grant all on sequence trips_id_seq to service_role;

-- Every assigned category is a leaf, and leaves have only one parent level.
create function enforce_category_tree() returns trigger language plpgsql as $$
declare parent categories%rowtype;
begin
  if new.parent_id is not null then
    select * into parent from categories where id = new.parent_id;
    if parent.parent_id is not null or parent.kind <> new.kind then
      raise exception 'Category parent must be a top-level category of the same kind';
    end if;
    if exists (select 1 from categories where parent_id = new.id) then
      raise exception 'A category with children cannot become a subcategory';
    end if;
  else
    if exists (select 1 from categories where parent_id = new.id and kind <> new.kind) then
      raise exception 'A parent category must have the same kind as its subcategories';
    end if;
    if exists (select 1 from transactions where category_id = new.id)
      or exists (select 1 from merchant_rules where set_category_id = new.id) then
      raise exception 'An assigned subcategory cannot become a parent category';
    end if;
  end if;
  return new;
end $$;
create trigger trg_category_tree before insert or update of parent_id, kind on categories
  for each row execute function enforce_category_tree();

create function enforce_assignable_category() returns trigger language plpgsql as $$
begin
  if new.category_id is not null and not exists
    (select 1 from categories where id = new.category_id and parent_id is not null) then
    raise exception 'Transactions must use a subcategory';
  end if;
  return new;
end $$;
create trigger trg_transaction_subcategory before insert or update of category_id on transactions
  for each row execute function enforce_assignable_category();

create function enforce_rule_subcategory() returns trigger language plpgsql as $$
begin
  if new.set_category_id is not null and not exists
    (select 1 from categories where id = new.set_category_id and parent_id is not null) then
    raise exception 'Merchant rules must use a subcategory';
  end if;
  return new;
end $$;
create trigger trg_merchant_rule_subcategory before insert or update of set_category_id on merchant_rules
  for each row execute function enforce_rule_subcategory();
revoke all on function enforce_category_tree(), enforce_assignable_category(), enforce_rule_subcategory()
  from public, anon, authenticated;
grant execute on function enforce_category_tree(), enforce_assignable_category(), enforce_rule_subcategory()
  to service_role;
