"use client"

import Link from "next/link"
import { ChevronDown } from "lucide-react"
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, XAxis, YAxis, type TooltipContentProps } from "recharts"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, useChartTooltipMotion } from "@/components/ui/chart"
import { ChartHeatGradient, HEAT_PIE_PALETTE, useHeatGradientId } from "@/components/ui/chart-heat-gradient"
import { money } from "@/lib/filters"
import type { buildTrendInsights, TrendMonth } from "@/lib/trends-insights"

type Insights = ReturnType<typeof buildTrendInsights>

const categoryColors = HEAT_PIE_PALETTE
const percent = new Intl.NumberFormat("de-DE", { style: "percent", maximumFractionDigits: 0 })

function monthLabel(month: string) {
  const date = new Date(`${month}-01T00:00:00Z`)
  return new Intl.DateTimeFormat("en-GB", { month: "short", year: "2-digit", timeZone: "UTC" }).format(date)
}

function axisMoney(value: number) {
  return Math.abs(value) >= 1000
    ? `${new Intl.NumberFormat("de-DE", { maximumFractionDigits: 1 }).format(value / 1000)}k €`
    : `${new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 }).format(value)} €`
}

function MonthTooltip({ active, payload }: TooltipContentProps) {
  const point = payload?.[0]?.payload as TrendMonth | undefined
  const tooltipRef = useChartTooltipMotion(Boolean(active && point))
  if (!active || !point) return null
  return <div ref={tooltipRef} className="grid min-w-44 max-w-72 gap-2 rounded-lg border border-border bg-background p-3 text-xs shadow-xl">
    <div className="font-medium leading-4">{monthLabel(point.month)}</div>
    <div className="flex items-center gap-2">
      <span className={point.partial ? "size-2.5 shrink-0 rounded-none border border-dashed border-[#1c69d4] bg-[#1c69d4]/25" : "size-2.5 shrink-0 rounded-none bg-[#1c69d4]"} />
      <span className="flex-1 text-muted-foreground">Net spend</span>
      <strong className="whitespace-nowrap font-mono font-medium tabular-nums">{money.format(point.spend)}</strong>
    </div>
    {point.partial && <div className="text-muted-foreground">Partial month in this selection</div>}
  </div>
}

function MetricCard({ label, value, detail }: { label: string; value: React.ReactNode; detail: React.ReactNode }) {
  return <section className="metric-cell" aria-label={label}>
    <h3 className="metric-label">{label}</h3>
    <div className={`metric-value ${label === "Largest category" ? "metric-value-text" : ""}`}>{value}</div>
    <div className="text-[10px] leading-relaxed text-muted-foreground">{detail}</div>
  </section>
}

function changeText(current: number, previous: number) {
  const change = current - previous
  const ratio = previous !== 0 ? Math.abs(change / previous) : null
  return <span className={change > 0 ? "text-destructive" : change < 0 ? "text-success" : undefined}>
    {change > 0 ? "↑" : change < 0 ? "↓" : "→"} {money.format(Math.abs(change))}{ratio !== null ? ` (${percent.format(ratio)})` : ""} vs previous month
  </span>
}

export function TrendsDashboard({ insights, uncategorizedHref }: { insights: Insights; uncategorizedHref: string }) {
  const heatGradientId = useHeatGradientId()
  const { months, total, completeCount, average, latest, previous, categories, changes, partialInsight } = insights
  const topCategory = categories[0]
  const hasPartial = months.some((month) => month.partial)

  return <div className="space-y-4">
    <div className="metric-grid" style={{ "--metric-count": 4 } as React.CSSProperties}>
      <MetricCard label="Total spent" value={money.format(total)} detail="Selected dates · after refunds" />
      <MetricCard label="Average full month" value={average == null ? "—" : money.format(average)} detail={completeCount ? `Across ${completeCount} complete ${completeCount === 1 ? "month" : "months"}` : "No complete months in this selection"} />
      <MetricCard label="Latest full month" value={latest ? money.format(latest.spend) : "—"} detail={latest ? <>{monthLabel(latest.month)}{previous ? <> · {changeText(latest.spend, previous.spend)}</> : " · no earlier full month to compare"}</> : "Choose a longer range to compare months"} />
      <MetricCard label="Largest category" value={topCategory?.category ?? "—"} detail={topCategory ? `${money.format(topCategory.spend)} · ${percent.format(topCategory.share)} of category spending` : "No category spending"} />
    </div>

    <Card>
      <CardHeader>
        <CardTitle>Monthly spending</CardTitle>
        <CardDescription>Net outflows after refunds. Compare full months against their average.</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="mb-3 flex flex-wrap gap-x-5 gap-y-2 text-xs text-muted-foreground" aria-label="Chart key">
          {completeCount > 0 && <span className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-sm bg-[#1c69d4]" />Full month</span>}
          {hasPartial && <span className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-sm border border-dashed border-[#1c69d4] bg-[#1c69d4]/25" />Partial month</span>}
          {average !== null && <span className="flex items-center gap-2"><span className="w-4 border-t-2 border-dashed border-muted-foreground" />Full-month average {money.format(average)}</span>}
        </div>
        <ChartContainer config={{ spend: { label: "Net spend", color: "#1c69d4" } }} className="h-72 w-full aspect-auto sm:h-80" role="group" aria-label="Net spending by month">
          <BarChart data={months} margin={{ top: 10, right: 10, left: 0, bottom: 0 }} accessibilityLayer>
            <defs><ChartHeatGradient id={heatGradientId} /></defs>
            <CartesianGrid vertical={false} strokeDasharray="3 3" />
            <XAxis dataKey="month" tickFormatter={monthLabel} tickLine={false} axisLine={false} minTickGap={12} tickMargin={8} />
            <YAxis tickFormatter={axisMoney} tickLine={false} axisLine={false} width={60} />
            <ChartTooltip content={MonthTooltip} cursor={{ fill: "var(--muted)", fillOpacity: 0.55 }} />
            {average !== null && <ReferenceLine y={average} stroke="var(--muted-foreground)" strokeDasharray="5 5" />}
            <Bar dataKey="spend" maxBarSize={54} radius={0}>
              {months.map((point) => <Cell key={point.month} fill={`url(#${heatGradientId})`} fillOpacity={point.partial ? 0.25 : 1} stroke={point.partial ? "#1c69d4" : "none"} strokeDasharray={point.partial ? "4 3" : undefined} />)}
            </Bar>
          </BarChart>
        </ChartContainer>
        {partialInsight && <div className="mt-3 rounded-lg bg-muted/60 px-3 py-2.5 text-sm leading-relaxed">
          <span className="font-medium">{monthLabel(partialInsight.month)} so far: {money.format(partialInsight.spend)}.</span>{" "}
          <span className="text-muted-foreground">The largest category is {partialInsight.category} at {money.format(partialInsight.categorySpend)}{partialInsight.categorySpend <= partialInsight.spend ? ` (${percent.format(partialInsight.categorySpend / partialInsight.spend)} of this month)` : ""}.</span>
        </div>}
        {hasPartial && <p className="mt-2 text-xs text-muted-foreground">Partial months are excluded from the average and month to month comparison.</p>}
      </CardContent>
    </Card>

    <div className="grid gap-4 xl:grid-cols-2">
      <Card>
        <CardHeader><CardTitle>Where your money went</CardTitle><CardDescription>Largest categories across the selected dates · share of category spending</CardDescription></CardHeader>
        <CardContent className="space-y-4">
          {categories.map((row, index) => <details key={row.category} className="group space-y-1.5">
            <summary className="flex cursor-pointer list-none items-baseline justify-between gap-3 rounded-sm text-sm focus-visible:outline-2 focus-visible:outline-primary [&::-webkit-details-marker]:hidden">
              <span className="flex min-w-0 items-center gap-1.5 truncate font-medium" title={row.category}><ChevronDown className="size-4 shrink-0 -rotate-90 self-center transition-transform group-open:rotate-0" />{row.category}</span>
              <span className="shrink-0 tabular-nums"><strong className="font-medium">{money.format(row.spend)}</strong><span className="ml-2 text-xs text-muted-foreground">{percent.format(row.share)}</span></span>
            </summary>
            <div className="h-2 w-full overflow-hidden rounded-none bg-muted" role="img" aria-label={`${row.category}: ${money.format(row.spend)}, ${percent.format(row.share)}`}>
              <div className="h-full rounded-none" style={{ width: `${Math.min(100, row.share * 100)}%`, backgroundColor: categoryColors[index % categoryColors.length] }} />
            </div>
            <div className="space-y-1 border-l pl-6 text-xs text-muted-foreground">{row.children.map((child) => <div key={child.category} className="flex justify-between gap-2"><span>{child.category}</span><span className="tabular-nums">{money.format(child.spend)}</span></div>)}</div>
          </details>)}
          {categories.some((row) => row.category === "Uncategorized") && <p className="border-t pt-3 text-xs text-muted-foreground">Uncategorized spending can hide useful patterns. <Link href={uncategorizedHref} className="font-medium text-foreground underline-offset-4 hover:underline">Review uncategorized transactions</Link>.</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>What changed</CardTitle><CardDescription>{latest && previous ? `${monthLabel(latest.month)} compared with ${monthLabel(previous.month)} · largest category changes` : "Compare the two most recent complete months"}</CardDescription></CardHeader>
        <CardContent>
          {latest && previous ? <>
            <div className="mb-4 rounded-lg bg-muted/60 px-3 py-2.5 text-sm">
              <span className="font-medium">{monthLabel(latest.month)} total: {money.format(latest.spend)}</span>
              <span className="ml-2 text-muted-foreground">{changeText(latest.spend, previous.spend)}</span>
            </div>
            {changes.length ? <div className="divide-y">{changes.map((row) => <details key={row.category} className="group py-3 first:pt-0 last:pb-0"><summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-sm focus-visible:outline-2 focus-visible:outline-primary [&::-webkit-details-marker]:hidden">
              <div className="min-w-0"><div className="flex items-center gap-1.5 truncate text-sm font-medium" title={row.category}><ChevronDown className="size-4 shrink-0 -rotate-90 transition-transform group-open:rotate-0" />{row.category}</div><div className="mt-0.5 pl-5.5 text-xs text-muted-foreground tabular-nums">{money.format(row.previous)} → {money.format(row.current)}</div></div>
              <span className={`shrink-0 text-sm font-medium tabular-nums ${row.change > 0 ? "text-destructive" : "text-success"}`}>{row.change > 0 ? "+" : "−"}{money.format(Math.abs(row.change))}</span>
            </summary><div className="mt-2 space-y-1 border-l pl-6 text-xs text-muted-foreground">{row.children.map((child) => <div key={child.category} className="flex justify-between gap-2"><span>{child.category}</span><span className="tabular-nums">{money.format(child.previous)} → {money.format(child.current)}</span></div>)}</div></details>)}</div> : <p className="text-sm text-muted-foreground">Category spending was unchanged across these months.</p>}
          </> : <p className="py-8 text-center text-sm text-muted-foreground">Choose a range with at least two complete months to see what drove the change.</p>}
        </CardContent>
      </Card>
    </div>
  </div>
}
