begin;

insert into categories (name, parent_id, kind, is_essential)
select 'Snacks', id, kind, false
from categories
where name = 'Food' and parent_id is null
on conflict (name) do nothing;

update transactions t
set category_id = snacks.id
from categories groceries, categories snacks
where t.category_id = groceries.id
  and groceries.name = 'Groceries'
  and snacks.name = 'Snacks'
  and coalesce(t.merchant, t.counterparty_raw, '') = 'GFM AUTOMATEN GMBH';

update merchant_rules r
set set_category_id = snacks.id
from categories groceries, categories snacks
where r.set_category_id = groceries.id
  and groceries.name = 'Groceries'
  and snacks.name = 'Snacks'
  and r.pattern = '^GFM AUTOMATEN GMBH$';

commit;
