import { Suspense } from "react"
import { DailyBarChart } from "@/components/dashboard-charts"
import { MonthlyCategoryTable } from "@/components/monthly-category-table"
import { DataTable } from "@/components/data-table"
import { EmptyState, PageHeading } from "@/components/dashboard-shell"
import { HousingUtilitiesToggle } from "@/components/housing-utilities-toggle"
import { MonthSelect } from "@/components/month-select"
import { SectionCards } from "@/components/section-cards"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { monthStart, param, resolveFilters, selectedMonth, type Params } from "@/lib/filters"
import { getAvailableMonths, getMonthly } from "@/lib/queries/monthly"
import { transactionOptions } from "@/lib/queries/transactions"

const monthFormatter = new Intl.DateTimeFormat("en-US", { month: "long", year: "numeric", timeZone: "UTC" })

export default async function MonthlyPage({ searchParams }: { searchParams: Promise<Params> }) {
  const params = await searchParams
  const account = resolveFilters(params).account
  const month = selectedMonth(params)
  const priorMonthLabel = monthFormatter.format(new Date(`${monthStart(month, -1)}T12:00:00Z`))
  const excludeHousing = param(params, "excludeHousing") !== "0"
  const options = transactionOptions(params)
  const [data, months] = await Promise.all([getMonthly(account, month, options, excludeHousing), getAvailableMonths(account)])
  const toggleQuery = new URLSearchParams({ month })
  if (account) toggleQuery.set("account", account)
  for (const key of ["sort", "dir", "group", "q", "type", "category"]) {
    const value = param(params, key)
    if (value) toggleQuery.set(key, value)
  }
  if (excludeHousing) toggleQuery.set("excludeHousing", "0")
  return <main className="space-y-4"><PageHeading title="Monthly" description={excludeHousing ? "Compare a month with the month before it, excluding Housing & Utilities spending." : "Compare a month with the month before it."} action={<div className="flex flex-wrap items-center gap-2"><HousingUtilitiesToggle href={`/monthly?${toggleQuery.toString()}`} excluded={excludeHousing} /><MonthSelect month={month} months={months} /></div>} />
    {data.current.count === 0 ? <EmptyState title="No transactions this month" description="Choose another month or account." /> : <>
      <div className="space-y-2">
        <SectionCards comparisonNoteId="monthly-comparison-note" metrics={[
          { label: "Spend", value: data.current.spend, previous: data.prior.spend, increaseBad: true },
          { label: "Income", value: data.current.income, previous: data.prior.income },
          { label: "Net", value: data.current.net, previous: data.prior.net },
        ]} />
        <p id="monthly-comparison-note" className="text-sm text-muted-foreground">* Compared with {priorMonthLabel}.</p>
      </div>
      <DailyBarChart data={data.daily} />
      <Card><CardHeader><CardTitle>Categories</CardTitle></CardHeader><CardContent><MonthlyCategoryTable groups={data.categories} /></CardContent></Card>
      <div className="space-y-3"><h2 className="text-lg font-medium">Transactions</h2><Suspense fallback={null}><DataTable key={options.search} {...data.transactions} options={options} /></Suspense></div>
    </>}
  </main>
}
