import "server-only"
import { db } from "@/lib/db"
import { monthStart, shiftDate } from "@/lib/filters"
import { getTransactions, type TransactionOptions } from "./transactions"
import type { Daily, Summary } from "./types"

export async function getAvailableMonths(account: string | null): Promise<string[]> {
  const rows = await db`select distinct to_char(month, 'YYYY-MM') as selected_month
    from v_transactions where (${account}::text is null or account_id = ${account})
    order by selected_month desc`
  return rows.map((row) => String(row.selected_month))
}

export async function getMonthly(account: string | null, month: string, options: TransactionOptions, excludeHousing = false) {
  const from = `${month}-01`
  const to = shiftDate(monthStart(from, 1), -1)
  const prevFrom = monthStart(from, -1)
  const [kpis, dailyRows, categoryRows, transactions] = await Promise.all([
    db`select
      coalesce(sum(case when d >= ${from}::date and type in ('expense','cash','fee','refund') then -amount else 0 end), 0)::float8 as spend,
      coalesce(sum(case when d >= ${from}::date and type = 'income' then amount else 0 end), 0)::float8 as income,
      coalesce(sum(case when d >= ${from}::date and type in ('income','expense','cash','fee','refund') then amount else 0 end), 0)::float8 as net,
      coalesce(sum(case when d < ${from}::date and type in ('expense','cash','fee','refund') then -amount else 0 end), 0)::float8 as prev_spend,
      coalesce(sum(case when d < ${from}::date and type = 'income' then amount else 0 end), 0)::float8 as prev_income,
      coalesce(sum(case when d < ${from}::date and type in ('income','expense','cash','fee','refund') then amount else 0 end), 0)::float8 as prev_net,
      count(*) filter (where d >= ${from}::date)::int as count
      from (select *, coalesce(transacted_at::date, booking_date) as d from v_transactions
        where (${account}::text is null or account_id = ${account})
          and coalesce(transacted_at::date, booking_date) between ${prevFrom}::date and ${to}::date
          and (not ${excludeHousing}::boolean or type not in ('expense','cash','fee','refund') or parent_category is distinct from 'Housing & Utilities')) t`,
    db`select to_char(coalesce(transacted_at::date, booking_date), 'YYYY-MM-DD') as date,
      sum(spend)::float8 as spend from v_spend
      where (${account}::text is null or account_id = ${account})
        and coalesce(transacted_at::date, booking_date) between ${from}::date and ${to}::date
        and (not ${excludeHousing}::boolean or parent_category is distinct from 'Housing & Utilities')
      group by 1 order by 1`,
    db`select coalesce(category, 'Uncategorized') as category, parent_category,
      sum(spend) filter (where d >= ${from}::date)::float8 as spend,
      sum(spend) filter (where d < ${from}::date)::float8 as previous
      from (select *, coalesce(transacted_at::date, booking_date) as d from v_spend
        where (${account}::text is null or account_id = ${account})
          and coalesce(transacted_at::date, booking_date) between ${prevFrom}::date and ${to}::date
          and (not ${excludeHousing}::boolean or parent_category is distinct from 'Housing & Utilities')) s
      group by 1, 2 order by coalesce(sum(spend) filter (where d >= ${from}::date), 0) desc`,
    getTransactions({ account, from, to }, options, excludeHousing),
  ])
  const row = kpis[0]
  const dailyMap = new Map((dailyRows as unknown as Daily[]).map((item) => [item.date, item.spend]))
  const daily: Daily[] = []
  for (let date = from; date <= to; date = shiftDate(date, 1)) {
    daily.push({ date, spend: dailyMap.get(date) ?? 0 })
  }
  return {
    current: { spend: row.spend, income: row.income, net: row.net, count: row.count } as Summary,
    prior: { spend: row.prev_spend, income: row.prev_income, net: row.prev_net, count: 0 } as Summary,
    daily,
    categories: (() => {
      const groups = new Map<string, { category: string; spend: number; previous: number; children: { category: string; spend: number; previous: number }[] }>()
      for (const item of categoryRows) {
        const root = String(item.parent_category ?? item.category)
        const group = groups.get(root) ?? { category: root, spend: 0, previous: 0, children: [] }
        const child = { category: String(item.category), spend: Number(item.spend ?? 0), previous: Number(item.previous ?? 0) }
        group.spend += child.spend
        group.previous += child.previous
        if (item.parent_category) group.children.push(child)
        groups.set(root, group)
      }
      return [...groups.values()].sort((a, b) => b.spend - a.spend)
    })(),
    transactions,
  }
}
