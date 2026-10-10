import "server-only"
import { db } from "@/lib/db"
import { param, type Filters, type Params } from "@/lib/filters"
import { getCategoryOptions } from "./categories"
import type { Transaction } from "./types"

const allowedTypes = new Set(["expense", "income", "transfer", "cash", "fee", "refund"])

export type TransactionOptions = {
  page: number; sort: "date" | "amount"; direction: "asc" | "desc"
  search: string; types: string[]; categories: string[]; groupBy: "none" | "day" | "week" | "month"
}

export function transactionOptions(params: Params): TransactionOptions {
  const page = Number(param(params, "page"))
  return {
    page: Number.isSafeInteger(page) && page > 0 ? Math.min(page, 100000) : 1,
    sort: param(params, "sort") === "amount" ? "amount" : "date",
    direction: param(params, "dir") === "asc" ? "asc" : "desc",
    search: (param(params, "q") ?? "").slice(0, 200),
    types: (param(params, "type") ?? "").split(",").filter((item) => allowedTypes.has(item)),
    categories: (param(params, "category") ?? "").split(",").filter(Boolean).slice(0, 50),
    groupBy: param(params, "group") === "day" ? "day" : param(params, "group") === "week" ? "week" : param(params, "group") === "month" ? "month" : "none",
  }
}

export async function getTransactions(filters: Filters, options: TransactionOptions, excludeHousing = false) {
  const { account, from, to } = filters
  const term = `%${options.search.replace(/[\\%_]/g, "\\$&")}%`
  const types = db.array(options.types)
  const categories = db.array(options.categories)
  const where = db`where (${account}::text is null or account_id = ${account})
    and (${from}::date is null or coalesce(transacted_at::date, booking_date) >= ${from}::date)
    and (${to}::date is null or coalesce(transacted_at::date, booking_date) <= ${to}::date)
    and (${options.search} = '' or merchant ilike ${term} escape '\' or counterparty_raw ilike ${term} escape '\' or description_raw ilike ${term} escape '\')
    and (cardinality(${types}::text[]) = 0 or type::text = any(${types}::text[]))
    and (cardinality(${categories}::text[]) = 0 or coalesce(category, 'Uncategorized') = any(${categories}::text[]) or coalesce(parent_category, 'Uncategorized') = any(${categories}::text[]))
    and (not ${excludeHousing}::boolean or type not in ('expense','cash','fee','refund') or parent_category is distinct from 'Housing & Utilities')`
  const order = options.sort === "amount" ? db`amount` : db`coalesce(transacted_at::date, booking_date)`
  const direction = options.direction === "asc" ? db`asc` : db`desc`
  const groupOrder = options.groupBy === "day"
    ? db`coalesce(transacted_at::date, booking_date)`
    : options.groupBy === "week"
      ? db`date_trunc('week', coalesce(transacted_at::date, booking_date)::timestamp)`
      : options.groupBy === "month"
        ? db`date_trunc('month', coalesce(transacted_at::date, booking_date)::timestamp)`
        : null
  const ordering = groupOrder
    ? db`${groupOrder} ${options.sort === "date" ? direction : db`desc`}, ${order} ${direction}`
    : db`${order} ${direction}`
  const [rows, counts, categoryOptions] = await Promise.all([
    db`select id::text as id, to_char(coalesce(transacted_at::date, booking_date), 'YYYY-MM-DD') as date,
         merchant, counterparty_raw, description_raw, category, parent_category, account_name,
         type::text as type, amount::float8 as amount, fee::float8 as fee, currency,
         original_amount::float8 as original_amount, original_currency, fx_rate::float8 as fx_rate,
         to_char(booking_date, 'YYYY-MM-DD') as booking_date,
         to_char(value_date, 'YYYY-MM-DD') as value_date, status::text as status
       from v_transactions ${where} order by ${ordering}, v_transactions.id desc
       limit 50 offset ${(options.page - 1) * 50}`,
    db`select count(*)::int as total from v_transactions ${where}`,
    getCategoryOptions(),
  ])
  return { rows: rows as unknown as Transaction[], total: Number(counts[0]?.total ?? 0), categories: categoryOptions }
}
