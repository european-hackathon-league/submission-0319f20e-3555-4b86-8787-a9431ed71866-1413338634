import { ChartAreaInteractive } from "@/components/chart-area-interactive"
import { CategoryDonut, HorizontalSpendChart, IncomeSpendChart } from "@/components/dashboard-charts"
import { EmptyState, PageHeading } from "@/components/dashboard-shell"
import { HousingUtilitiesToggle } from "@/components/housing-utilities-toggle"
import { SectionCards } from "@/components/section-cards"
import { globalFilterQuery, param, resolveFilters, type Params } from "@/lib/filters"
import { getOverview } from "@/lib/queries/overview"

export default async function OverviewPage({ searchParams }: { searchParams: Promise<Params> }) {
  const params = await searchParams
  const filters = resolveFilters(params)
  const excludeHousing = param(params, "excludeHousing") !== "0"
  const data = await getOverview(filters, excludeHousing)
  const toggleQuery = new URLSearchParams(globalFilterQuery(params))
  if (excludeHousing) toggleQuery.set("excludeHousing", "0")
  const query = toggleQuery.toString()
  const toggleHref = query ? `/?${query}` : "/"

  return <main className="space-y-4"><PageHeading
    title="Overview"
    description={excludeHousing ? "A snapshot of your money, excluding Housing & Utilities spending." : "A snapshot of your money across the selected accounts and dates."}
    action={<HousingUtilitiesToggle href={toggleHref} excluded={excludeHousing} />}
  />
    {data.current.count === 0 ? <EmptyState /> : <>
      <div className="space-y-2"><SectionCards comparisonNoteId={data.prior ? "overview-comparison-note" : undefined} metrics={[
        { label: "Total spend", value: data.current.spend, previous: data.prior?.spend, increaseBad: true },
        { label: "Income", value: data.current.income, previous: data.prior?.income },
        { label: "Net", value: data.current.net, previous: data.prior?.net },
        { label: "Transactions", value: data.current.count, previous: data.prior?.count, format: "count" },
      ]} />
      {data.prior && <p id="overview-comparison-note" className="text-sm text-muted-foreground">* Compared with the same number of days right before the dates you&apos;re viewing. For example, the last 6 months vs. the 6 months before that.</p>}</div>
      <ChartAreaInteractive data={data.daily} from={filters.from} to={filters.to} />
      <div className="grid gap-4 xl:grid-cols-2"><IncomeSpendChart data={data.monthly} /><CategoryDonut data={data.categories} /></div>
      <HorizontalSpendChart title="Top merchants" description="Top 10 by total spend" data={data.merchants} />
    </>}
  </main>
}
