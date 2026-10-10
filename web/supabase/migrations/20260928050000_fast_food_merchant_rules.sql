begin;

-- Remember the prepared-food vendors already represented by historical transactions.
insert into merchant_rules (priority, match_field, pattern, set_category_id, note)
select 100, 'merchant', x.pattern, c.id, 'Fast Food vendor'
from (values
  ($pattern$^Choripan$$pattern$),
  ($pattern$^Joe's Pizza$$pattern$),
  ($pattern$^L'Industrie Pizzeria$$pattern$),
  ($pattern$^Scarr's Pizza$$pattern$)
) as x(pattern)
cross join categories c
where c.name = 'Fast Food'
  and not exists (
    select 1 from merchant_rules r
    where r.match_field = 'merchant'
      and r.pattern = x.pattern
      and r.set_category_id = c.id
  );

commit;
