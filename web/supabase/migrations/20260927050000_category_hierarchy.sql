-- Two levels only: broad parent categories and assignable subcategories.
begin;

insert into categories (name, kind, is_essential) values
  ('Food', 'spend', false),
  ('Entertainment', 'spend', false),
  ('Software & Subscriptions', 'spend', false),
  ('Finance', 'spend', null),
  ('Income', 'income', null),
  ('Transfers', 'transfer', null),
  ('Other', 'other', null),
  ('Transport', 'spend', true)
on conflict (name) do nothing;

-- Existing category IDs are retained so merchant rules and transactions remain valid.
with changes(old_name, new_name, parent_name) as (values
  ('Restaurants & Cafes', 'Restaurants', 'Food'),
  ('Food Delivery', 'Delivery', 'Food'),
  ('Taxi & Rideshare', 'Taxi & Rideshare', 'Transport'),
  ('Subscriptions & Software', 'Other Subscriptions', 'Software & Subscriptions'),
  ('Phone & Internet', 'Internet & Phone', 'Housing & Utilities'),
  ('Entertainment & Events', 'Events', 'Entertainment'),
  ('Cash', 'Cash Withdrawals', 'Finance'),
  ('Fees', 'Bank Fees', 'Finance'),
  ('Salary', 'Salary', 'Income'),
  ('Freelance', 'Freelance', 'Income'),
  ('Family', 'Family', 'Income'),
  ('Cashback & Rewards', 'Cashback & Rewards', 'Income'),
  ('Other Income', 'Other Income', 'Income'),
  ('Internal Transfer', 'Internal Transfer', 'Transfers'),
  ('Uncategorized', 'Uncategorized', 'Other'),
  ('Snacks', 'Snacks', 'Food'),
  ('Cannabis', 'Cannabis', 'Health & Personal Care'),
  ('Music', 'Music', 'Entertainment'),
  ('Investments', 'Investments', 'Finance'),
  ('AI Tools', 'AI Tools', 'Software & Subscriptions')
)
update categories c set name = x.new_name, parent_id = p.id
from changes x join categories p on p.name = x.parent_name
where c.name = x.old_name;

insert into categories (name, parent_id, kind, is_essential)
select x.name, p.id, p.kind, x.is_essential
from (values
  ('Supermarkets', 'Groceries', true),
  ('Convenience Stores', 'Groceries', false),
  ('Cafes', 'Food', false),
  ('Bakeries', 'Food', false),
  ('Public Transport', 'Transport', true),
  ('Micromobility', 'Transport', false),
  ('Car Sharing', 'Transport', false),
  ('Fuel', 'Transport', true),
  ('General Shopping', 'Shopping', false),
  ('Clothing', 'Shopping', false),
  ('Sports & Outdoors', 'Shopping', false),
  ('Software', 'Software & Subscriptions', false),
  ('Memberships', 'Software & Subscriptions', false),
  ('Rent', 'Housing & Utilities', true),
  ('Utilities', 'Housing & Utilities', true),
  ('Broadcasting Fees', 'Housing & Utilities', true),
  ('Fitness', 'Health & Personal Care', true),
  ('Pharmacy', 'Health & Personal Care', true),
  ('Hair & Beauty', 'Health & Personal Care', false),
  ('Other Health', 'Health & Personal Care', true),
  ('Recreation', 'Entertainment', false),
  ('Games', 'Entertainment', false),
  ('Other Travel', 'Travel', false),
  ('Courses & Learning', 'Education', true),
  ('Gifts', 'Gifts & Friends', false)
) as x(name, parent_name, is_essential)
join categories p on p.name = x.parent_name
on conflict (name) do nothing;

-- Default mapping follows the old category. These exceptions use known merchant rules
-- to give specifically classified merchants a useful second level.
with exceptions(rule_id, leaf) as (values
  (16, 'Bakeries'), (34, 'Cafes'), (52, 'Cafes'), (56, 'Bakeries'),
  (58, 'Bakeries'), (60, 'Bakeries'), (68, 'Convenience Stores'),
  (78, 'Bakeries'), (84, 'Cafes'), (96, 'Cafes'), (97, 'Convenience Stores'),
  (102, 'Bakeries'), (103, 'Cafes'), (113, 'Bakeries'),
  (2, 'Micromobility'), (17, 'Micromobility'), (21, 'Car Sharing'),
  (39, 'Micromobility'), (53, 'Fuel'), (54, 'Micromobility'),
  (64, 'Micromobility'), (76, 'Micromobility'), (105, 'Micromobility'),
  (51, 'Clothing'), (85, 'Clothing'), (100, 'Sports & Outdoors'),
  (101, 'Clothing'), (10, 'Rent'), (11, 'Internet & Phone'),
  (70, 'Broadcasting Fees'), (72, 'Broadcasting Fees'),
  (32, 'Fitness'), (65, 'Fitness'), (67, 'Fitness'), (93, 'Fitness'),
  (98, 'Hair & Beauty'), (111, 'Pharmacy'), (112, 'Pharmacy'),
  (71, 'Recreation'), (89, 'Games'),
  (62, 'Software'), (77, 'Software'), (116, 'Memberships'),
  (24, 'General Shopping'), (45, 'General Shopping'), (95, 'General Shopping')
)
update merchant_rules r set set_category_id = c.id
from exceptions e join categories c on c.name = e.leaf
where r.id = e.rule_id;

with defaults(root, leaf) as (values
  ('Groceries', 'Supermarkets'), ('Transport', 'Public Transport'),
  ('Shopping', 'General Shopping'), ('Housing & Utilities', 'Utilities'),
  ('Health & Personal Care', 'Other Health'), ('Travel', 'Other Travel'),
  ('Education', 'Courses & Learning'), ('Gifts & Friends', 'Gifts')
)
update merchant_rules r set set_category_id = leaf.id
from categories old join defaults d on d.root = old.name
join categories leaf on leaf.name = d.leaf
where r.set_category_id = old.id;

-- Reapply the now-specific merchant rules to the existing rule-classified rows.
with matched as (
  select t.id, (
    select r.set_category_id from merchant_rules r
    where r.set_category_id is not null
      and (r.account_id is null or r.account_id = t.account_id)
      and (case r.match_field
        when 'merchant' then t.merchant
        when 'counterparty_raw' then t.counterparty_raw
        when 'description_raw' then t.description_raw
        when 'source_type' then t.source_type end) ~* r.pattern
    order by r.priority, r.id limit 1
  ) as leaf_id
  from transactions t where t.category_source = 'rule'
)
update transactions t set category_id = m.leaf_id
from matched m where t.id = m.id and m.leaf_id is not null
  and t.category_id is distinct from m.leaf_id;

with defaults(root, leaf) as (values
  ('Groceries', 'Supermarkets'), ('Transport', 'Public Transport'),
  ('Shopping', 'General Shopping'), ('Housing & Utilities', 'Utilities'),
  ('Health & Personal Care', 'Other Health'), ('Travel', 'Other Travel'),
  ('Education', 'Courses & Learning'), ('Gifts & Friends', 'Gifts')
)
update transactions t set category_id = leaf.id
from categories old join defaults d on d.root = old.name
join categories leaf on leaf.name = d.leaf
where t.category_id = old.id;

create index if not exists categories_parent_id_idx on categories(parent_id);
alter table categories add constraint categories_not_self_parent check (parent_id is null or parent_id <> id);

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
  and t.parent_category is distinct from 'Housing & Utilities';
alter view v_trip_transactions set (security_invoker = true);

create or replace view v_category_monthly as
select month,
       coalesce(category, 'Uncategorized') as category,
       coalesce(parent_category, 'Other') as parent_category,
       sum(spend) as spend,
       count(*) as txn_count
from v_spend
group by month, coalesce(category, 'Uncategorized'), coalesce(parent_category, 'Other')
order by month, spend desc;
alter view v_category_monthly set (security_invoker = true);

-- Importer's automatic labels retain their names, but now resolve to leaves.
commit;
