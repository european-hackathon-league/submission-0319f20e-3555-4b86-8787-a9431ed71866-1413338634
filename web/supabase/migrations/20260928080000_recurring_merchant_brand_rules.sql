begin;

-- Replace brittle exact merchant-name rules with brand-level matches for
-- recurring businesses. Match both the normalized merchant and raw counterparty
-- so country-specific legal entities and payment descriptions still resolve.
with legacy_brands(pattern, category_name) as (
  values
    ('REWE', 'Groceries'),
    ('LIDL', 'Groceries'),
    ('ALCAMPO', 'Groceries'),
    ('MCDONALD', 'Restaurants'),
    ('WOLT', 'Delivery'),
    ('UBER', 'Taxi & Rideshare'),
    ('UBER', 'Delivery'),
    ('UBER', 'Other Subscriptions'),
    ('TELEKOM', 'Internet & Phone'),
    ('PYUR', 'Internet & Phone'),
    ('SPOTIFY', 'Other Subscriptions'),
    ('TRADE.?REPUBLIC', 'Investments'),
    ('MILES', 'Other Transport'),
    ('GFM.?AUTOMATEN', 'Snacks'),
    ('HIGGSFIELD', 'AI Tools'),
    ('CURSOR', 'AI Tools'),
    ('OPENAI|CHATGPT', 'AI Tools'),
    ('EUKIA', 'Rent'),
    ('FITNESS.?FIRST', 'Fitness'),
    ('ALADIN.*HEADSHOP', 'Shopping'),
    ('TORROS.*GRILL', 'Restaurants'),
    ('LUFTHANSA', 'Planes & Trains'),
    ('DEUTSCHE.?BAHN|DB.?VERTRIEB', 'Planes & Trains'),
    ('(^|[^A-Z0-9])MTA([^A-Z0-9]|$)', 'Public Transport'),
    ('BAECKEREI.?KONDITOREI.?ZIEGLE', 'Cafe / Bakery'),
    ('MCOS.*BEHANDLUNGSGEBUEH', 'Weed')
)
delete from merchant_rules r
using categories c, legacy_brands b
where r.set_category_id = c.id
  and c.name = b.category_name
  and r.match_field in ('merchant', 'counterparty_raw')
  and r.pattern ~* b.pattern;

with brands(pattern, set_merchant, category_name, priority, note) as (
  values
    ('REWE', 'REWE', 'Groceries', 10, 'Normalize REWE locations and legal-entity variants.'),
    ('LIDL', 'Lidl', 'Groceries', 10, 'Normalize Lidl locations and legal-entity variants.'),
    ('ALCAMPO', 'Alcampo', 'Groceries', 10, 'Normalize Alcampo locations and legal-entity variants.'),
    ('MCDONALD', 'McDonald''s', 'Fast Food', 10, 'Route McDonald''s to Fast Food across location variants.'),
    ('WOLT', 'Wolt', 'Delivery', 10, 'Normalize Wolt locations and legal-entity variants.'),
    ('UBER.*EATS', 'Uber Eats', 'Delivery', 5, 'Match Uber Eats before generic Uber ride charges.'),
    ('UBER.*ONE', 'Uber One', 'Other Subscriptions', 5, 'Match Uber One before generic Uber ride charges.'),
    ('UBER.*DIRECT', 'Uber Direct', 'Taxi & Rideshare', 5, 'Keep Uber Direct separate from Uber Eats and rides.'),
    ('UBER', 'Uber', 'Taxi & Rideshare', 20, 'Normalize Uber ride and legal-entity variants.'),
    ('TELEKOM', 'Telekom', 'Internet & Phone', 10, 'Normalize Telekom billing-name variants.'),
    ('PYUR', 'PYUR', 'Internet & Phone', 10, 'Normalize PYUR billing-name variants.'),
    ('SPOTIFY', 'Spotify', 'Other Subscriptions', 10, 'Normalize Spotify billing-name variants.'),
    ('TRADE.?REPUBLIC', 'Trade Republic', 'Investments', 10, 'Normalize Trade Republic billing-name variants.'),
    ('MILES', 'MILES', 'Other Transport', 10, 'Normalize MILES mobility billing-name variants.'),
    ('GFM.?AUTOMATEN', 'GFM Automaten', 'Snacks', 10, 'Normalize GFM vending-machine billing variants.'),
    ('HIGGSFIELD', 'Higgsfield', 'AI Tools', 10, 'Normalize Higgsfield billing-name variants.'),
    ('(^|[^A-Z0-9])CURSOR([^A-Z0-9]|$)', 'Cursor', 'AI Tools', 10, 'Normalize Cursor billing-name variants.'),
    ('OPENAI|CHATGPT', 'OpenAI', 'AI Tools', 10, 'Normalize OpenAI and ChatGPT billing-name variants.'),
    ('EUKIA', 'Eukia', 'Rent', 10, 'Normalize Eukia property-management billing variants.'),
    ('FITNESS.?FIRST', 'Fitness First', 'Fitness', 10, 'Normalize Fitness First billing-name variants.'),
    ('ALADIN.*HEADSHOP', 'Aladin Headshop', 'Shopping', 10, 'Normalize Aladin Headshop billing-name variants.'),
    ('TORROS.*GRILL', 'Torros Grill House', 'Restaurants', 10, 'Normalize Torros Grill House and payment-terminal variants.'),
    ('LUFTHANSA', 'Lufthansa', 'Planes & Trains', 10, 'Match Lufthansa ticket and billing-name variants.'),
    ('DEUTSCHE.?BAHN|DB.?VERTRIEB', 'Deutsche Bahn', 'Planes & Trains', 10, 'Normalize Deutsche Bahn and DB Vertrieb variants.'),
    ('(^|[^A-Z0-9])MTA([^A-Z0-9]|$)', 'MTA', 'Public Transport', 10, 'Match MTA public-transport charges as a complete token.'),
    ('BAECKEREI.?KONDITOREI.?ZIEGLE', 'Bäckerei Ziegle', 'Cafe / Bakery', 10, 'Normalize Bäckerei Ziegle location variants.'),
    ('MCOS.*BEHANDLUNGSGEBUEH', 'MCOS', 'Weed', 10, 'Normalize recurring MCOS dispensary charges.')
), expanded_rules as (
  select f.match_field, b.pattern, b.set_merchant, b.category_name,
         b.priority, b.note
  from brands b
  cross join (values ('merchant'), ('counterparty_raw')) as f(match_field)
)
insert into merchant_rules (priority, match_field, pattern, set_merchant, set_category_id, note)
select r.priority, r.match_field, r.pattern, r.set_merchant, c.id, r.note
from expanded_rules r
join categories c on c.name = r.category_name;

-- Re-run brand rules against history. Keep explicit manual category choices,
-- while replacing prior automatic guesses with the brand's assigned category.
with matched as (
  select t.id, r.set_merchant, r.set_category_id
  from transactions t
  cross join lateral (
    select mr.set_merchant, mr.set_category_id
    from merchant_rules mr
    where (mr.account_id is null or mr.account_id = t.account_id)
      and case mr.match_field
        when 'merchant' then t.merchant
        when 'counterparty_raw' then t.counterparty_raw
        when 'description_raw' then t.description_raw
        when 'source_type' then t.source_type
      end ~* mr.pattern
    order by mr.priority asc, mr.id asc
    limit 1
  ) r
)
update transactions t
set merchant = coalesce(m.set_merchant, t.merchant),
    category_id = case
      when t.category_source is distinct from 'manual' then coalesce(m.set_category_id, t.category_id)
      else t.category_id
    end,
    category_source = case
      when t.category_source is distinct from 'manual' and m.set_category_id is not null then 'rule'::category_source
      else t.category_source
    end,
    needs_review = case
      when t.category_source is distinct from 'manual' and m.set_category_id is not null then false
      else t.needs_review
    end
from matched m
where m.id = t.id;

commit;
