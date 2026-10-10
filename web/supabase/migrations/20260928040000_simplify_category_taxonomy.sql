begin;

-- Rename broad groups first; their child IDs remain stable for views and subscriptions.
update categories set name = 'Subscriptions'
where name = 'Software & Subscriptions' and parent_id is null;

update categories set name = 'Health'
where name = 'Health & Personal Care' and parent_id is null;

-- Keep the existing supermarket leaf as the single Groceries category under Food.
update categories set name = 'Groceries (legacy)'
where name = 'Groceries' and parent_id is null;

update categories as leaf
set name = 'Groceries', parent_id = parent.id, kind = parent.kind
from categories as parent
where leaf.name = 'Supermarkets'
  and parent.name = 'Food' and parent.parent_id is null;

-- Rename the categories that remain, and add the few useful consolidated destinations.
update categories set name = 'Scooters & E-bikes'
where name = 'Micromobility';

update categories set name = 'Weed'
where name = 'Cannabis';

update categories set name = 'Cash & Fees'
where name = 'Cash Withdrawals';

insert into categories (name, parent_id, kind, is_essential)
select x.name, p.id, p.kind, x.is_essential
from (values
  ('Fast Food', 'Food', false),
  ('Other Transport', 'Transport', false),
  ('Planes & Trains', 'Transport', false)
) as x(name, parent_name, is_essential)
join categories p on p.name = x.parent_name and p.parent_id is null
on conflict (name) do nothing;

-- Keep vending, markets, and deli purchases with Groceries. Route pizza counters
-- and Choripan to Fast Food so the new category starts with useful history.
update transactions t
set category_id = case
  when coalesce(t.merchant, t.counterparty_raw, '') ~* '(pizzeria|pizza|choripan)' then fast_food.id
  else groceries.id
end
from categories snacks
cross join categories groceries
cross join categories fast_food
where t.category_id = snacks.id
  and snacks.name = 'Snacks'
  and groceries.name = 'Groceries'
  and fast_food.name = 'Fast Food';

-- Remap legacy transactions, merchant rules, and subscription records to the smaller set.
with mappings(source_name, target_name) as (values
  ('Convenience Stores', 'Groceries'),
  ('Clothing', 'Shopping'),
  ('Events', 'Going Out'),
  ('Recreation', 'Going Out'),
  ('Games', 'Other Subscriptions'),
  ('Music', 'Other Subscriptions'),
  ('Software', 'Other Subscriptions'),
  ('Memberships', 'Other Subscriptions'),
  ('Car Sharing', 'Other Transport'),
  ('Fuel', 'Other Transport'),
  ('Other Travel', 'Planes & Trains'),
  ('Pharmacy', 'Other Health'),
  ('Hair & Beauty', 'Other Health'),
  ('Bank Fees', 'Cash & Fees')
)
update transactions t
set category_id = target.id
from mappings m
join categories source on source.name = m.source_name
join categories target on target.name = m.target_name
where t.category_id = source.id;

with mappings(source_name, target_name) as (values
  ('Convenience Stores', 'Groceries'),
  ('Snacks', 'Groceries'),
  ('Clothing', 'Shopping'),
  ('Events', 'Going Out'),
  ('Recreation', 'Going Out'),
  ('Games', 'Other Subscriptions'),
  ('Music', 'Other Subscriptions'),
  ('Software', 'Other Subscriptions'),
  ('Memberships', 'Other Subscriptions'),
  ('Car Sharing', 'Other Transport'),
  ('Fuel', 'Other Transport'),
  ('Other Travel', 'Planes & Trains'),
  ('Pharmacy', 'Other Health'),
  ('Hair & Beauty', 'Other Health'),
  ('Bank Fees', 'Cash & Fees')
)
update merchant_rules r
set set_category_id = target.id
from mappings m
join categories source on source.name = m.source_name
join categories target on target.name = m.target_name
where r.set_category_id = source.id;

with mappings(source_name, target_name) as (values
  ('Convenience Stores', 'Groceries'),
  ('Snacks', 'Groceries'),
  ('Clothing', 'Shopping'),
  ('Events', 'Going Out'),
  ('Recreation', 'Going Out'),
  ('Games', 'Other Subscriptions'),
  ('Music', 'Other Subscriptions'),
  ('Software', 'Other Subscriptions'),
  ('Memberships', 'Other Subscriptions'),
  ('Car Sharing', 'Other Transport'),
  ('Fuel', 'Other Transport'),
  ('Other Travel', 'Planes & Trains'),
  ('Pharmacy', 'Other Health'),
  ('Hair & Beauty', 'Other Health'),
  ('Bank Fees', 'Cash & Fees')
)
update subscriptions s
set category_id = target.id
from mappings m
join categories source on source.name = m.source_name
join categories target on target.name = m.target_name
where s.category_id = source.id;

-- Spotify and Chess.com were sitting in entertainment; subscriptions is the useful view.
update merchant_rules r
set set_category_id = target.id
from categories source, categories target
where source.name = 'Scooters & E-bikes'
  and target.name = 'Taxi & Rideshare'
  and r.set_category_id = source.id
  and r.pattern ~* 'lyft';

update transactions t
set category_id = target.id
from categories source, categories target
where source.name = 'Scooters & E-bikes'
  and target.name = 'Taxi & Rideshare'
  and t.category_id = source.id
  and coalesce(t.merchant, t.counterparty_raw, '') ~* '^Lyft$';

update merchant_rules r
set set_category_id = target.id
from categories source, categories target
where source.name = 'Public Transport'
  and target.name = 'Planes & Trains'
  and r.set_category_id = source.id
  and r.pattern ~* 'DB Vertrieb';

update transactions t
set category_id = target.id
from categories source, categories target
where source.name = 'Public Transport'
  and target.name = 'Planes & Trains'
  and t.category_id = source.id
  and coalesce(t.merchant, t.counterparty_raw, '') ~* 'DB Vertrieb';

-- Education, Gifts, and explicit Uncategorized are not separate spending categories.
-- Leave any old assignments in the review queue so the user can recategorize them.
update transactions t
set category_id = null, category_source = null, needs_review = true
from categories source
where t.category_id = source.id
  and source.name in ('Courses & Learning', 'Gifts', 'Uncategorized');

update subscriptions s
set category_id = null
from categories source
where s.category_id = source.id
  and source.name in ('Courses & Learning', 'Gifts', 'Uncategorized');

delete from merchant_rules r
using categories source
where r.set_category_id = source.id
  and source.name in ('Courses & Learning', 'Gifts', 'Uncategorized');

-- Remove the categories that have been merged or intentionally dropped.
delete from categories where name in (
  'Convenience Stores', 'Snacks', 'Clothing', 'Events', 'Games', 'Music', 'Recreation',
  'Software', 'Memberships', 'Car Sharing', 'Fuel', 'Other Travel', 'Pharmacy',
  'Hair & Beauty', 'Bank Fees', 'Courses & Learning', 'Gifts', 'Uncategorized'
);

delete from categories where name in ('Groceries (legacy)', 'Travel', 'Education', 'Gifts & Friends', 'Other');

-- Uncategorized has no parent category; keep that visible through the existing reporting view.
create or replace view v_category_monthly as
select month,
       coalesce(category, 'Uncategorized') as category,
       parent_category,
       sum(spend) as spend,
       count(*) as txn_count
from v_spend
group by month, coalesce(category, 'Uncategorized'), parent_category
order by month, spend desc;
alter view v_category_monthly set (security_invoker = true);

commit;
