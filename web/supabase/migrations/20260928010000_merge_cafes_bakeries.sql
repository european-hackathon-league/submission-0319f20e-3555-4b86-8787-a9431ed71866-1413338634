begin;

insert into categories (name, parent_id, kind, is_essential)
select 'Cafe / Bakery', p.id, p.kind, false
from categories p
where p.name = 'Food' and p.parent_id is null
on conflict (name) do nothing;

with target as (
  select id from categories where name = 'Cafe / Bakery'
), sources as (
  select id from categories where name in ('Cafes', 'Bakeries')
)
update transactions t
set category_id = target.id
from target
where t.category_id in (select id from sources);

with target as (
  select id from categories where name = 'Cafe / Bakery'
), sources as (
  select id from categories where name in ('Cafes', 'Bakeries')
)
update merchant_rules r
set set_category_id = target.id
from target
where r.set_category_id in (select id from sources);

do $$
begin
  if to_regclass('public.subscriptions') is not null then
    execute $statement$
      with target as (
        select id from categories where name = 'Cafe / Bakery'
      ), sources as (
        select id from categories where name in ('Cafes', 'Bakeries')
      )
      update subscriptions s
      set category_id = target.id
      from target
      where s.category_id in (select id from sources)
    $statement$;
  end if;
end $$;

delete from categories where name in ('Cafes', 'Bakeries');

commit;
