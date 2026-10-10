begin;

-- Replace store- and ride-description-specific matches with brand-level rules.
delete from merchant_rules r
using categories c
where r.set_category_id = c.id
  and c.name in ('Groceries', 'Scooters & E-bikes')
  and r.match_field in ('merchant', 'counterparty_raw')
  and r.pattern ~* '(edeka|lime)';

insert into merchant_rules (priority, match_field, pattern, set_merchant, set_category_id, note)
select 10, x.match_field, x.pattern, x.set_merchant, c.id, x.note
from (values
  ('merchant', 'EDEKA', 'EDEKA', 'Groceries', 'Normalize EDEKA store and legal-entity variants.'),
  ('counterparty_raw', 'EDEKA', 'EDEKA', 'Groceries', 'Catch EDEKA named in the raw counterparty.'),
  ('merchant', 'LIME', 'Lime', 'Scooters & E-bikes', 'Normalize Lime ride, pass, and legal-entity variants.'),
  ('counterparty_raw', 'LIME', 'Lime', 'Scooters & E-bikes', 'Catch Lime named in the raw counterparty.')
) as x(match_field, pattern, set_merchant, category_name, note)
join categories c on c.name = x.category_name;

-- Apply those rules to historical transactions too, while retaining manual choices.
update transactions t
set merchant = 'EDEKA',
    category_id = case when t.category_source is distinct from 'manual' then c.id else t.category_id end,
    category_source = case when t.category_source is distinct from 'manual' then 'rule'::category_source else t.category_source end,
    needs_review = case when t.category_source is distinct from 'manual' then false else t.needs_review end
from categories c
where c.name = 'Groceries'
  and (coalesce(t.merchant, '') ~* 'EDEKA' or coalesce(t.counterparty_raw, '') ~* 'EDEKA');

update transactions t
set merchant = 'Lime',
    category_id = case when t.category_source is distinct from 'manual' then c.id else t.category_id end,
    category_source = case when t.category_source is distinct from 'manual' then 'rule'::category_source else t.category_source end,
    needs_review = case when t.category_source is distinct from 'manual' then false else t.needs_review end
from categories c
where c.name = 'Scooters & E-bikes'
  and (coalesce(t.merchant, '') ~* 'LIME' or coalesce(t.counterparty_raw, '') ~* 'LIME');

commit;
