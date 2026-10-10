"use client"

import { useState, type ReactNode } from "react"
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, XAxis, YAxis } from "recharts"
import { ChevronDown } from "lucide-react"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartLegend, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { ChartHeatGradient, COOL_GRADIENT_CSS, HEAT_GRADIENT_CSS, HEAT_PIE_PALETTE, useHeatGradientId } from "@/components/ui/chart-heat-gradient"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { formatDate, money } from "@/lib/filters"
import type { CategorySpend, Daily, MerchantSpend, Monthly, Subscription } from "@/lib/queries/types"

function titleMonth(value: string) { return `${value.slice(5, 7)}.${value.slice(0, 4)}` }
function tooltip() { return <ChartTooltipContent labelFormatter={(value) => /^\d{4}-\d{2}$/.test(String(value)) ? titleMonth(String(value)) : String(value)} formatter={(value) => money.format(Number(value))} /> }

const percent = new Intl.NumberFormat("de-DE", { style: "percent", maximumFractionDigits: 1 })

function categoryTooltip(total: number) {
  return <ChartTooltipContent hideLabel formatter={(value) => {
    const amount = Number(value)
    return <span className="flex flex-col items-end">
      <span>{money.format(amount)}</span>
      <span className="text-[10px] font-normal text-muted-foreground">{percent.format(total ? amount / total : 0)} of total spend</span>
    </span>
  }} />
}

function IncomeSpendLegend() {
  return <div className="flex items-center justify-center gap-4 pt-3">
    <span className="flex items-center gap-1.5 text-sm"><span className="size-2.5 shrink-0 rounded-sm" style={{ background: COOL_GRADIENT_CSS }} />Income</span>
    <span className="flex items-center gap-1.5 text-sm"><span className="size-2.5 shrink-0 rounded-sm" style={{ background: HEAT_GRADIENT_CSS }} />Spend</span>
  </div>
}

export function IncomeSpendChart({ data }: { data: Monthly[] }) {
  const incomeGradientId = useHeatGradientId()
  const spendGradientId = useHeatGradientId()
  return <Card><CardHeader><CardTitle>Income vs spend</CardTitle><CardDescription>Monthly totals</CardDescription></CardHeader><CardContent>
    <ChartContainer config={{ income: { label: "Income", color: "#65778f" }, spend: { label: "Spend", color: "#1c69d4" } }} className="h-72 w-full aspect-auto">
      <BarChart data={data}>
        <defs><ChartHeatGradient id={incomeGradientId} tone="cool" /><ChartHeatGradient id={spendGradientId} /></defs>
        <CartesianGrid vertical={false} /><XAxis dataKey="month" tickFormatter={titleMonth} tickLine={false} axisLine={false} /><YAxis tickFormatter={(v: number) => `${v} €`} tickLine={false} axisLine={false} width={55} /><ChartTooltip content={tooltip()} /><ChartLegend content={<IncomeSpendLegend />} />
        <Bar dataKey="income" fill="#65778f" radius={0}>{data.map((row) => <Cell key={row.month} fill={`url(#${incomeGradientId})`} />)}</Bar>
        <Bar dataKey="spend" fill="#1c69d4" radius={0}>{data.map((row) => <Cell key={row.month} fill={`url(#${spendGradientId})`} />)}</Bar>
      </BarChart>
    </ChartContainer>
  </CardContent></Card>
}

export function CategoryDonut({ data }: { data: CategorySpend[] }) {
  const total = data.reduce((sum, row) => sum + row.spend, 0)
  const otherSpend = data.slice(6).reduce((sum, row) => sum + row.spend, 0)
  const pieData = [...data.slice(0, 6), ...(otherSpend > 0 ? [{ category: "Other categories", spend: otherSpend, children: [] }] : [])]
    .map((row, i) => ({ ...row, key: `c${i}`, fill: HEAT_PIE_PALETTE[i % HEAT_PIE_PALETTE.length] }))
  const config: ChartConfig = Object.fromEntries(pieData.map((row) => [row.key, { label: row.category, color: row.fill }]))
  return <Card><CardHeader><CardTitle>Spend by category</CardTitle><CardDescription>Top six categories and other</CardDescription></CardHeader><CardContent>
    <div className="relative"><ChartContainer config={config} className="mx-auto h-60 w-full aspect-auto">
      <PieChart>
        <ChartTooltip content={categoryTooltip(total)} /><Pie data={pieData} dataKey="spend" nameKey="category" innerRadius={75} outerRadius={105} strokeWidth={2}>{pieData.map((row) => <Cell key={row.key} fill={row.fill} />)}</Pie>
      </PieChart>
    </ChartContainer><div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center"><span className="text-xs text-muted-foreground">Total spend</span><strong className="text-lg tabular-nums">{money.format(total)}</strong></div></div>
    <div className="mt-3 grid gap-2 sm:grid-cols-2">{data.map((row, index) => <details key={row.category} className="group min-w-0 text-sm"><summary className="flex cursor-pointer list-none items-center gap-2 rounded-sm focus-visible:outline-2 focus-visible:outline-primary [&::-webkit-details-marker]:hidden"><span className="size-2.5 shrink-0 rounded-sm" style={{ background: HEAT_PIE_PALETTE[Math.min(index, 6) % HEAT_PIE_PALETTE.length] }} /><span className="min-w-0 flex-1 truncate">{row.category}</span><span className="font-medium tabular-nums">{money.format(row.spend)}</span><ChevronDown className="size-4 shrink-0 -rotate-90 transition-transform group-open:rotate-0" /></summary><div className="mt-1 space-y-1 border-l pl-4 text-muted-foreground">{row.children.map((child) => <div key={child.category} className="flex justify-between gap-2"><span>{child.category}</span><span className="tabular-nums">{money.format(child.spend)}</span></div>)}</div></details>)}</div>
  </CardContent></Card>
}

export function HorizontalSpendChart({ title, description, data, action }: { title: string; description?: string; data: MerchantSpend[]; action?: ReactNode }) {
  const heatGradientId = useHeatGradientId()
  return <Card><CardHeader><CardTitle>{title}</CardTitle>{description && <CardDescription>{description}</CardDescription>}{action && <CardAction>{action}</CardAction>}</CardHeader><CardContent>
    {data.length === 0 ? <p className="flex h-40 items-center justify-center text-sm text-muted-foreground">No spending in this selection.</p> :
    <ChartContainer config={{ spend: { label: "Spend", color: "#1c69d4" } }} className="w-full aspect-auto" style={{ height: Math.max(260, data.length * 34) }}>
      <BarChart data={data} layout="vertical" margin={{ right: 22 }}>
        <defs><ChartHeatGradient id={heatGradientId} direction="horizontal" /></defs>
        <CartesianGrid horizontal={false} /><XAxis type="number" tickFormatter={(v: number) => `${v} €`} tickLine={false} axisLine={false} /><YAxis type="category" dataKey="merchant" width={135} tickFormatter={(v: string) => v.length > 18 ? `${v.slice(0, 17)}…` : v} tickLine={false} axisLine={false} /><ChartTooltip content={tooltip()} />
        <Bar dataKey="spend" fill="var(--chart-2)" radius={0}>{data.map((row) => <Cell key={row.merchant} fill={`url(#${heatGradientId})`} />)}</Bar>
      </BarChart>
    </ChartContainer>}
  </CardContent></Card>
}

export function DailyBarChart({ data }: { data: Daily[] }) {
  const heatGradientId = useHeatGradientId()
  return <Card><CardHeader><CardTitle>Daily spend</CardTitle><CardDescription>Spending during the selected month</CardDescription></CardHeader><CardContent>
    <ChartContainer config={{ spend: { label: "Spend", color: "#1c69d4" } }} className="h-72 w-full aspect-auto"><BarChart data={data}>
      <defs><ChartHeatGradient id={heatGradientId} /></defs>
      <CartesianGrid vertical={false} /><XAxis dataKey="date" tickFormatter={(v: string) => v.slice(8)} tickLine={false} axisLine={false} /><YAxis tickFormatter={(v: number) => `${v} €`} tickLine={false} axisLine={false} width={55} /><ChartTooltip content={<ChartTooltipContent labelFormatter={(v) => formatDate(String(v))} formatter={(v) => money.format(Number(v))} />} />
      <Bar dataKey="spend" fill={`url(#${heatGradientId})`} radius={0} />
    </BarChart></ChartContainer>
  </CardContent></Card>
}

export function SubscriptionCostChart({ rows }: { rows: Subscription[] }) {
  const [period, setPeriod] = useState<"monthly" | "yearly">("yearly")
  const data = rows
    .filter((row) => row.status === "active" && row.yearly_cost != null)
    .map((row) => ({ merchant: row.name, spend: period === "yearly" ? row.yearly_cost! : row.yearly_cost! / 12 }))
    .sort((a, b) => b.spend - a.spend)

  return <HorizontalSpendChart
    title={`${period === "yearly" ? "Yearly" : "Monthly"} cost by subscription`}
    description="Current cost for active subscriptions"
    data={data}
    action={<ToggleGroup value={[period]} onValueChange={(values) => {
      if (values[0] === "monthly" || values[0] === "yearly") setPeriod(values[0])
    }} variant="outline" size="sm" spacing={0} aria-label="Subscription cost period">
      <ToggleGroupItem value="monthly">Monthly</ToggleGroupItem>
      <ToggleGroupItem value="yearly">Yearly</ToggleGroupItem>
    </ToggleGroup>}
  />
}
