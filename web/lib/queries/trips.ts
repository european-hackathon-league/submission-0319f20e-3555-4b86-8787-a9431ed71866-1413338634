import "server-only"
import { db } from "@/lib/db"
import { groupCategorySpend } from "@/lib/category-groups"
import { shiftDate } from "@/lib/filters"
import type { TransactionOptions } from "./transactions"
import { getCategoryOptions } from "./categories"
import type { Transaction } from "./types"

export type Trip = {
  id: string; name: string; destination: string | null; start_date: string
  end_date: string; notes: string | null; days: number; txn_count: number
  total_spend: number; avg_per_day: number; cash: number; fees: number
}
export type TripTransaction = Transaction & { manually_added: boolean; overridden: boolean }
export type ExcludedTransaction = Pick<Transaction, "id" | "date" | "merchant" | "counterparty_raw" | "amount" | "account_name"> & { in_date_range: boolean }
export type CandidateTransaction = Omit<ExcludedTransaction, "in_date_range"> & { category: string | null }

const tripColumns = db`trip_id::text as id, name, destination,
  to_char(start_date, 'YYYY-MM-DD') as start_date,
  to_char(end_date, 'YYYY-MM-DD') as end_date, notes,
  days::int as days, txn_count::int as txn_count,
  total_spend::float8 as total_spend, avg_per_day::float8 as avg_per_day,
  cash::float8 as cash, fees::float8 as fees`

export async function getTrips(): Promise<Trip[]> {
  const rows = await db`select ${tripColumns} from v_trip_summary order by start_date desc, trip_id desc`
  return rows as unknown as Trip[]
}

export async function getTrip(id: string): Promise<Trip | null> {
  const rows = await db`select ${tripColumns} from v_trip_summary where trip_id = ${id}::bigint`
  return (rows[0] as Trip | undefined) ?? null
}

export async function getTripAnalytics(id: string) {
  const [dailyRows, categoryRows, merchantRows, accountRows, outsideRows] = await Promise.all([
    db`select to_char(d.day, 'YYYY-MM-DD') as date, coalesce(sum(v.spend), 0)::float8 as spend
       from trips tr cross join lateral generate_series(tr.start_date, tr.end_date, interval '1 day') as d(day)
       left join v_trip_transactions v on v.trip_id = tr.id and v.txn_date = d.day::date
       where tr.id = ${id}::bigint group by d.day order by d.day`,
    db`select coalesce(category, 'Uncategorized') as category, parent_category, sum(spend)::float8 as spend
       from v_trip_transactions where trip_id = ${id}::bigint
       group by 1, 2 order by spend desc`,
    db`select coalesce(merchant, counterparty_raw, 'Unknown') as merchant, sum(spend)::float8 as spend
       from v_trip_transactions where trip_id = ${id}::bigint
       group by coalesce(merchant, counterparty_raw, 'Unknown') order by spend desc limit 10`,
    db`select account_name as account, sum(spend)::float8 as spend
       from v_trip_transactions where trip_id = ${id}::bigint
       group by account_name order by spend desc`,
    db`select count(*)::int as count from v_trip_transactions v
       join trips tr on tr.id = v.trip_id
       where v.trip_id = ${id}::bigint and v.manually_added
         and (v.txn_date < tr.start_date or v.txn_date > tr.end_date)`,
  ])
  return {
    daily: dailyRows as unknown as { date: string; spend: number }[],
    categories: groupCategorySpend(categoryRows as unknown as { category: string; parent_category: string | null; spend: number }[]),
    merchants: merchantRows as unknown as { merchant: string; spend: number }[],
    accounts: accountRows as unknown as { account: string; spend: number }[],
    outsideCount: Number(outsideRows[0]?.count ?? 0),
  }
}

export async function getTripTransactions(id: string, options: TransactionOptions) {
  const term = `%${options.search.replace(/[\\%_]/g, "\\$&")}%`
  const types = db.array(options.types)
  const categories = db.array(options.categories)
  const where = db`where v.trip_id = ${id}::bigint
    and (${options.search} = '' or v.merchant ilike ${term} escape '\' or v.counterparty_raw ilike ${term} escape '\' or v.description_raw ilike ${term} escape '\')
    and (cardinality(${types}::text[]) = 0 or v.type::text = any(${types}::text[]))
    and (cardinality(${categories}::text[]) = 0 or coalesce(v.category, 'Uncategorized') = any(${categories}::text[]) or coalesce(v.parent_category, 'Uncategorized') = any(${categories}::text[]))`
  const order = options.sort === "amount" ? db`v.amount` : db`v.txn_date`
  const direction = options.direction === "asc" ? db`asc` : db`desc`
  const groupOrder = options.groupBy === "day"
    ? db`v.txn_date`
    : options.groupBy === "week"
      ? db`date_trunc('week', v.txn_date::timestamp)`
      : options.groupBy === "month"
        ? db`date_trunc('month', v.txn_date::timestamp)`
        : null
  const ordering = groupOrder
    ? db`${groupOrder} ${options.sort === "date" ? direction : db`desc`}, ${order} ${direction}`
    : db`${order} ${direction}`
  const [rows, counts, categoryOptions] = await Promise.all([
    db`select v.id::text as id, to_char(v.txn_date, 'YYYY-MM-DD') as date,
         v.merchant, v.counterparty_raw, v.description_raw, v.category, v.parent_category, v.account_name,
         v.type::text as type, v.amount::float8 as amount, v.fee::float8 as fee, v.currency,
         v.original_amount::float8 as original_amount, v.original_currency, v.fx_rate::float8 as fx_rate,
         to_char(v.booking_date, 'YYYY-MM-DD') as booking_date,
         to_char(v.value_date, 'YYYY-MM-DD') as value_date, v.status::text as status,
         v.manually_added, (o.included is not null) as overridden
       from v_trip_transactions v left join trip_transactions o
         on o.trip_id = v.trip_id and o.transaction_id = v.id
       ${where} order by ${ordering}, v.id desc limit 50 offset ${(options.page - 1) * 50}`,
    db`select count(*)::int as total from v_trip_transactions v ${where}`,
    getCategoryOptions("spend"),
  ])
  return {
    rows: rows as unknown as TripTransaction[],
    total: Number(counts[0]?.total ?? 0),
    categories: categoryOptions,
  }
}

export async function getExcludedTransactions(id: string): Promise<ExcludedTransaction[]> {
  const rows = await db`select t.id::text as id,
      to_char(coalesce(t.transacted_at::date, t.booking_date), 'YYYY-MM-DD') as date,
      t.merchant, t.counterparty_raw, t.amount::float8 as amount, t.account_name,
      (coalesce(t.transacted_at::date, t.booking_date) between tr.start_date and tr.end_date) as in_date_range
    from trip_transactions o join v_transactions t on t.id = o.transaction_id
    join trips tr on tr.id = o.trip_id
    where o.trip_id = ${id}::bigint and not o.included
      and t.parent_category is distinct from 'Housing & Utilities'
    order by coalesce(t.transacted_at::date, t.booking_date) desc, t.id desc`
  return rows as unknown as ExcludedTransaction[]
}

export async function getCandidateTransactions(
  id: string, startDate: string, endDate: string, search: string,
): Promise<CandidateTransaction[]> {
  const term = `%${search.replace(/[\\%_]/g, "\\$&")}%`
  const rows = await db`select t.id::text as id,
      to_char(coalesce(t.transacted_at::date, t.booking_date), 'YYYY-MM-DD') as date,
      t.merchant, t.counterparty_raw, t.amount::float8 as amount, t.account_name, t.category
    from v_transactions t join trips tr on tr.id = ${id}::bigint
    where t.type in ('expense', 'cash', 'fee', 'refund')
      and t.parent_category is distinct from 'Housing & Utilities'
      and coalesce(t.transacted_at::date, t.booking_date) between ${startDate}::date and ${endDate}::date
      and coalesce(t.transacted_at::date, t.booking_date) not between tr.start_date and tr.end_date
      and not exists (select 1 from trip_transactions o where o.trip_id = tr.id and o.transaction_id = t.id and o.included)
      and (${search} = '' or t.merchant ilike ${term} escape '\' or t.counterparty_raw ilike ${term} escape '\' or t.description_raw ilike ${term} escape '\')
    order by coalesce(t.transacted_at::date, t.booking_date) desc, t.id desc limit 100`
  return rows as unknown as CandidateTransaction[]
}

export function defaultCandidateRange(trip: Trip) {
  return { from: shiftDate(trip.start_date, -60), to: shiftDate(trip.start_date, -1) }
}
