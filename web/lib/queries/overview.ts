import "server-only"
import { db } from "@/lib/db"
import { groupCategorySpend } from "@/lib/category-groups"
import { previousRange, type Filters, type Range } from "@/lib/filters"
import type { CategorySpend, Daily, MerchantSpend, Monthly, Summary } from "./types"

async function summary(account: string | null, range: Range, excludeHousing: boolean): Promise<Summary> {
  const rows = await db`
    select
      coalesce(sum(case when type in ('expense','cash','fee','refund') then -amount else 0 end), 0)::float8 as spend,
      coalesce(sum(case when type = 'income' then amount else 0 end), 0)::float8 as income,
      coalesce(sum(case when type in ('income','expense','cash','fee','refund') then amount else 0 end), 0)::float8 as net,
      count(*)::int as count
    from v_transactions
    where (${account}::text is null or account_id = ${account})
      and (${range.from}::date is null or coalesce(transacted_at::date, booking_date) >= ${range.from}::date)
      and (${range.to}::date is null or coalesce(transacted_at::date, booking_date) <= ${range.to}::date)
      and (not ${excludeHousing}::boolean or type not in ('expense','cash','fee','refund') or parent_category is distinct from 'Housing & Utilities')
  `
  return rows[0] as Summary
}

export async function getOverview(filters: Filters, excludeHousing = false) {
  const { account, from, to } = filters
  const previous = previousRange(filters)
  const [current, prior, dailyRows, monthlyRows, categoryRows, merchantRows] = await Promise.all([
    summary(account, filters, excludeHousing),
    previous ? summary(account, previous, excludeHousing) : Promise.resolve(null),
    db`select to_char(coalesce(transacted_at::date, booking_date), 'YYYY-MM-DD') as date,
         sum(spend)::float8 as spend
       from v_spend
       where (${account}::text is null or account_id = ${account})
         and (${from}::date is null or coalesce(transacted_at::date, booking_date) >= ${from}::date)
         and (${to}::date is null or coalesce(transacted_at::date, booking_date) <= ${to}::date)
         and (not ${excludeHousing}::boolean or parent_category is distinct from 'Housing & Utilities')
         and spend > 0
       group by 1 order by 1`,
    db`select to_char(month, 'YYYY-MM') as month,
         sum(case when type in ('expense','cash','fee','refund') then -amount else 0 end)::float8 as spend,
         sum(case when type = 'income' then amount else 0 end)::float8 as income,
         sum(case when type in ('income','expense','cash','fee','refund') then amount else 0 end)::float8 as net
       from v_transactions
       where (${account}::text is null or account_id = ${account})
         and (${from}::date is null or coalesce(transacted_at::date, booking_date) >= ${from}::date)
         and (${to}::date is null or coalesce(transacted_at::date, booking_date) <= ${to}::date)
         and (not ${excludeHousing}::boolean or type not in ('expense','cash','fee','refund') or parent_category is distinct from 'Housing & Utilities')
       group by month order by month`,
    db`select coalesce(category, 'Uncategorized') as category, parent_category, sum(spend)::float8 as spend
       from v_spend
       where (${account}::text is null or account_id = ${account})
         and (${from}::date is null or coalesce(transacted_at::date, booking_date) >= ${from}::date)
         and (${to}::date is null or coalesce(transacted_at::date, booking_date) <= ${to}::date)
         and (not ${excludeHousing}::boolean or parent_category is distinct from 'Housing & Utilities')
       group by 1, 2 having sum(spend) > 0 order by spend desc`,
    db`select coalesce(nullif(merchant, ''), nullif(counterparty_raw, ''), 'Unknown') as merchant,
         sum(spend)::float8 as spend
       from v_spend
       where (${account}::text is null or account_id = ${account})
         and (${from}::date is null or coalesce(transacted_at::date, booking_date) >= ${from}::date)
         and (${to}::date is null or coalesce(transacted_at::date, booking_date) <= ${to}::date)
         and (not ${excludeHousing}::boolean or parent_category is distinct from 'Housing & Utilities')
       group by 1 having sum(spend) > 0 order by spend desc limit 10`,
  ])
  const categories = groupCategorySpend(categoryRows as unknown as { category: string; parent_category: string | null; spend: number }[])
  return {
    current, prior,
    daily: dailyRows as unknown as Daily[], monthly: monthlyRows as unknown as Monthly[],
    categories: categories satisfies CategorySpend[],
    merchants: merchantRows as unknown as MerchantSpend[],
  }
}
