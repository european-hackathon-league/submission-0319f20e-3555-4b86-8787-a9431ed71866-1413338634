import { Suspense } from "react"
import { DataTable } from "@/components/data-table"
import { PageHeading } from "@/components/dashboard-shell"
import { resolveFilters, type Params } from "@/lib/filters"
import { getTransactions, transactionOptions } from "@/lib/queries/transactions"

export default async function TransactionsPage({ searchParams }: { searchParams: Promise<Params> }) {
  const params = await searchParams
  const filters = resolveFilters(params)
  const options = transactionOptions(params)
  const data = await getTransactions(filters, options)
  return <main className="space-y-4"><PageHeading title="Transactions" description="Search, inspect, and quickly recategorize booked transactions." />
    <Suspense fallback={null}><DataTable key={options.search} {...data} options={options} /></Suspense>
  </main>
}
