begin;

comment on view v_recurring is 'Detected recurring transaction patterns only; not an authoritative subscription inventory.';

create table if not exists subscriptions (
  id             bigserial primary key,
  name           text not null unique,
  merchant_match text not null,
  category_id    int references categories(id),
  cadence        text not null check (cadence in ('weekly', 'monthly', 'quarterly', 'yearly')),
  amount         numeric(12,2) not null default 0 check (amount >= 0),
  currency       char(3) not null default 'EUR',
  status         text not null default 'active' check (status in ('active', 'paused', 'cancelled')),
  notes          text,
  sort_order     int not null default 100,
  created_at     timestamptz not null default now()
);
comment on table subscriptions is 'User-maintained subscriptions. Membership and status are independent of transaction frequency.';

alter table subscriptions enable row level security;
revoke all on subscriptions from anon, authenticated;
revoke all on sequence subscriptions_id_seq from anon, authenticated;
grant all on subscriptions to service_role;
grant all on sequence subscriptions_id_seq to service_role;

insert into subscriptions (name, merchant_match, category_id, cadence, amount, status, notes, sort_order)
select x.name, x.merchant_match, c.id, x.cadence, x.amount, x.status, x.notes, x.sort_order
from (values
  ('Rent', 'Eukia Vermietungs- und Verwaltungs GmbH', 'Rent', 'monthly', 1090.00::numeric, 'active', null::text, 1),
  ('PYUR Wi-Fi', 'PYUR', 'Internet & Phone', 'monthly', 24.99::numeric, 'active', null::text, 2),
  ('Spotify', 'Spotify', 'Music', 'monthly', 6.99::numeric, 'active', null::text, 3),
  ('Cursor', 'CURSOR, AI POWERED IDE', 'AI Tools', 'monthly', 0.00::numeric, 'active', 'Student trial; currently billed at €0.', 4),
  ('Fitness First', 'Fitness First', 'Fitness', 'monthly', 39.80::numeric, 'paused', null::text, 5),
  ('Claude', 'ANTHROPIC', 'AI Tools', 'monthly', 21.42::numeric, 'active', null::text, 6)
) as x(name, merchant_match, category_name, cadence, amount, status, notes, sort_order)
join categories c on c.name = x.category_name
on conflict (name) do update set
  merchant_match = excluded.merchant_match,
  category_id = excluded.category_id,
  cadence = excluded.cadence,
  amount = excluded.amount,
  status = excluded.status,
  notes = excluded.notes,
  sort_order = excluded.sort_order;

commit;
