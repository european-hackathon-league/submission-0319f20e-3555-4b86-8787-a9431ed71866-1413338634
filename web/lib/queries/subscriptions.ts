import "server-only"
import { db } from "@/lib/db"
import type { Subscription } from "./types"

export async function getSubscriptions() {
  const rows = await db`select s.id::text, s.name, c.name as category, p.name as parent_category,
      s.cadence, s.amount::float8 as amount, s.currency,
      (s.amount * case s.cadence when 'weekly' then 52 when 'monthly' then 12
        when 'quarterly' then 4 when 'yearly' then 1 end)::float8 as yearly_cost,
      to_char(last_payment.last_charge, 'YYYY-MM-DD') as last_charge,
      s.status, s.notes
    from subscriptions s
    left join categories c on c.id = s.category_id
    left join categories p on p.id = c.parent_id
    left join lateral (
      select max(t.booking_date) as last_charge
      from v_spend t
      where t.spend > 0
        and (t.merchant ilike '%' || s.merchant_match || '%'
          or t.counterparty_raw ilike '%' || s.merchant_match || '%')
    ) last_payment on true
    order by (s.status = 'active') desc, s.sort_order, s.name`
  return rows as unknown as Subscription[]
}
