import { TrendsDashboard } from "@/components/trends-dashboard"
import { EmptyState, PageHeading } from "@/components/dashboard-shell"
import { resolveFilters, type Params } from "@/lib/filters"
import { getTrends } from "@/lib/queries/trends"
import { buildTrendInsights } from "@/lib/trends-insights"

export default async function TrendsPage({ searchParams }: { searchParams: Promise<Params> }) {
  const filters = resolveFilters(await searchParams, "12m")
  const data = await getTrends(filters)
  const insights = buildTrendInsights(data.monthly, data.categories, filters)
  const uncategorizedQuery = new URLSearchParams({ category: "Uncategorized", type: "expense,cash,fee,refund" })
  if (filters.account) uncategorizedQuery.set("account", filters.account)
  if (filters.from && filters.to) {
    uncategorizedQuery.set("from", filters.from)
    uncategorizedQuery.set("to", filters.to)
  } else {
    uncategorizedQuery.set("range", "all")
  }
  return <main className="space-y-5"><PageHeading title="Trends" description="See how much you spend, where it goes, and what changed." />
    {data.monthly.length === 0 ? <EmptyState /> : <>
      <TrendsDashboard insights={insights} uncategorizedHref={`/transactions?${uncategorizedQuery.toString()}`} />
    </>}
  </main>
}
