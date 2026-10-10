begin;

-- Turn the old Shopping parent into a leaf category under Entertainment.
-- Keep the existing specific assignments as sibling leaves for clarity.
update categories
set name = 'Shopping (legacy)'
where name = 'Shopping' and parent_id is null;

update categories
set name = 'Shopping'
where name = 'General Shopping'
  and parent_id = (select id from categories where name = 'Shopping (legacy)' and parent_id is null);

update categories as c
set parent_id = entertainment.id, kind = entertainment.kind
from categories as legacy, categories as entertainment
where c.parent_id = legacy.id
  and legacy.name = 'Shopping (legacy)' and legacy.parent_id is null
  and entertainment.name = 'Entertainment' and entertainment.parent_id is null
  and c.name in ('Shopping', 'Clothing', 'Sports & Outdoors');

-- Preserve any references that pointed at the former non-assignable parent.
with ids as (
  select legacy.id as legacy_id, leaf.id as leaf_id
  from categories as legacy
  join categories as entertainment on entertainment.name = 'Entertainment' and entertainment.parent_id is null
  join categories as leaf on leaf.name = 'Shopping' and leaf.parent_id = entertainment.id
  where legacy.name = 'Shopping (legacy)' and legacy.parent_id is null
)
update transactions as t
set category_id = ids.leaf_id
from ids
where t.category_id = ids.legacy_id;

with ids as (
  select legacy.id as legacy_id, leaf.id as leaf_id
  from categories as legacy
  join categories as entertainment on entertainment.name = 'Entertainment' and entertainment.parent_id is null
  join categories as leaf on leaf.name = 'Shopping' and leaf.parent_id = entertainment.id
  where legacy.name = 'Shopping (legacy)' and legacy.parent_id is null
)
update merchant_rules as r
set set_category_id = ids.leaf_id
from ids
where r.set_category_id = ids.legacy_id;

do $$
begin
  if to_regclass('public.subscriptions') is not null then
    execute $statement$
      with ids as (
        select legacy.id as legacy_id, leaf.id as leaf_id
        from categories as legacy
        join categories as entertainment on entertainment.name = 'Entertainment' and entertainment.parent_id is null
        join categories as leaf on leaf.name = 'Shopping' and leaf.parent_id = entertainment.id
        where legacy.name = 'Shopping (legacy)' and legacy.parent_id is null
      )
      update subscriptions as s
      set category_id = ids.leaf_id
      from ids
      where s.category_id = ids.legacy_id
    $statement$;
  end if;
end $$;

delete from categories where name = 'Shopping (legacy)' and parent_id is null;

commit;
