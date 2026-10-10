import "server-only"
import { db } from "@/lib/db"
import type { Filters } from "@/lib/filters"

export async function getTrends(filters: Filters) {
  const { account, from, to } = filters
  const [categoryRows, monthlyRows] = await Promise.all([
    db`select to_char(month, 'YYYY-MM') as month, coalesce(category, 'Uncategorized') as category, parent_category,
      sum(spend)::float8 as spend from v_spend
      where (${account}::text is null or account_id = ${account})
        and (${from}::date is null or coalesce(transacted_at::date, booking_date) >= ${from}::date)
        and (${to}::date is null or coalesce(transacted_at::date, booking_date) <= ${to}::date)
      group by month, coalesce(category, 'Uncategorized'), parent_category order by month`,
    db`select to_char(month, 'YYYY-MM') as month, sum(spend)::float8 as spend
      from v_spend
      where (${account}::text is null or account_id = ${account})
        and (${from}::date is null or coalesce(transacted_at::date, booking_date) >= ${from}::date)
        and (${to}::date is null or coalesce(transacted_at::date, booking_date) <= ${to}::date)
      group by month order by month`,
  ])
  return {
    categories: categoryRows as unknown as { month: string; category: string; parent_category: string | null; spend: number }[],
    monthly: monthlyRows as unknown as { month: string; spend: number }[],
  }
}
