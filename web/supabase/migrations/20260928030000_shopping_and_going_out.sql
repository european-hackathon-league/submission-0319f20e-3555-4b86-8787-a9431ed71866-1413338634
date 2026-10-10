begin;

insert into categories (name, parent_id, kind, is_essential)
select 'Going Out', id, kind, false
from categories
where name = 'Entertainment' and parent_id is null
on conflict (name) do nothing;

-- Keep Clothing distinct, and combine general and outdoors shopping in Shopping.
with target as (
  select id from categories
  where name = 'Shopping'
    and parent_id = (select id from categories where name = 'Entertainment' and parent_id is null)
), sources as (
  select id from categories where name = 'Sports & Outdoors'
)
update transactions as t
set category_id = target.id
from target
where t.category_id in (select id from sources);

with target as (
  select id from categories
  where name = 'Shopping'
    and parent_id = (select id from categories where name = 'Entertainment' and parent_id is null)
), sources as (
  select id from categories where name = 'Sports & Outdoors'
)
update merchant_rules as r
set set_category_id = target.id
from target
where r.set_category_id in (select id from sources);

do $$
begin
  if to_regclass('public.subscriptions') is not null then
    execute $statement$
      with target as (
        select id from categories
        where name = 'Shopping'
          and parent_id = (select id from categories where name = 'Entertainment' and parent_id is null)
      ), sources as (
        select id from categories where name = 'Sports & Outdoors'
      )
      update subscriptions as s
      set category_id = target.id
      from target
      where s.category_id in (select id from sources)
    $statement$;
  end if;
end $$;

delete from categories where name = 'Sports & Outdoors';

commit;
