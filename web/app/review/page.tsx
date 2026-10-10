import { Suspense } from "react"
import { DataTable } from "@/components/data-table"
import { EmptyState, PageHeading } from "@/components/dashboard-shell"
import { resolveFilters, type Params } from "@/lib/filters"
import { getTransactions, transactionOptions } from "@/lib/queries/transactions"

export default async function ReviewPage({ searchParams }: { searchParams: Promise<Params> }) {
  const params = await searchParams
  const filters = resolveFilters(params)
  const options = transactionOptions({ ...params, category: params.category ?? "Uncategorized" })
  const data = await getTransactions(filters, options)
  return <main className="space-y-4">
    <PageHeading title="Review" description="Inspect uncategorized transactions and assign them to the right category." />
    {data.total === 0 && !options.search && options.categories.join() === "Uncategorized"
      ? <EmptyState title="Every transaction has a category" description="There are no uncategorized transactions in this account and date range." />
      : <Suspense fallback={null}><DataTable key={options.search} {...data} options={options} /></Suspense>}
  </main>
}
