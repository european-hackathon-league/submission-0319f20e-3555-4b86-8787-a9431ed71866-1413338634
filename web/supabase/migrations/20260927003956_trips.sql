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
where coalesce(o.included, true);
comment on view v_trip_transactions is 'All transactions per trip: spend types dated within the trip range, plus manual includes, minus manual excludes. spend is positive for outflows.';

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
