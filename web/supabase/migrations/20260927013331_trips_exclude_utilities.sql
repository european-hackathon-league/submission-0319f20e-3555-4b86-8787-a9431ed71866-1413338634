create or replace view v_trip_transactions as
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
  and t.category is distinct from 'Housing & Utilities';
comment on view v_trip_transactions is 'All transactions per trip: spend types dated within the trip range, plus manual includes, minus manual excludes. Housing & Utilities is excluded. spend is positive for outflows.';
alter view v_trip_transactions set (security_invoker = true);
