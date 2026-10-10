import { SubscriptionCostChart } from "@/components/dashboard-charts"
import { EmptyState, PageHeading } from "@/components/dashboard-shell"
import { HousingUtilitiesToggle } from "@/components/housing-utilities-toggle"
import { SubscriptionTable } from "@/components/subscription-table"
import { SectionCards } from "@/components/section-cards"
import { param, type Params } from "@/lib/filters"
import { getSubscriptions } from "@/lib/queries/subscriptions"

export const dynamic = "force-dynamic"

export default async function RecurringPage({ searchParams }: { searchParams: Promise<Params> }) {
  const params = await searchParams
  const hideUtilities = param(params, "excludeHousing") === "1"
  const allRows = await getSubscriptions()
  const rows = allRows.filter((row) => !hideUtilities || row.parent_category !== "Housing & Utilities")
  const active = rows.filter((row) => row.status === "active")
  const paused = rows.filter((row) => row.status === "paused")
  const currentYearly = active.reduce((sum, row) => sum + (row.yearly_cost ?? 0), 0)
  const pausedYearly = paused.reduce((sum, row) => sum + (row.yearly_cost ?? 0), 0)
  return <main className="space-y-4"><PageHeading title="Subscriptions" description="Your subscriptions and memberships, including trials and paused plans." action={<HousingUtilitiesToggle href={hideUtilities ? "/recurring" : "/recurring?excludeHousing=1"} excluded={hideUtilities} />} />
    {rows.length === 0 ? <EmptyState title="No subscriptions yet" description="Add the services and memberships you want to keep track of." /> : <>
      <SectionCards metrics={[
        { label: "Active subscriptions", value: active.length, format: "count" },
        { label: "Current monthly cost", value: currentYearly / 12 },
        { label: "Current yearly cost", value: currentYearly },
        { label: "Paused plan benchmark", value: pausedYearly },
      ]} />
      <SubscriptionTable rows={rows} />
      {active.some((row) => row.yearly_cost != null) && <SubscriptionCostChart rows={rows} />}
    </>}
  </main>
}
