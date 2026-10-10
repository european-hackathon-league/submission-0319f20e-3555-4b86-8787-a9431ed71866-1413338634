"use client"

import { Bar, BarChart, CartesianGrid, Cell, XAxis, YAxis } from "recharts"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartLegend, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart"
import { ChartHeatGradient, COOL_GRADIENT_CSS, HEAT_GRADIENT_CSS, useHeatGradientId } from "@/components/ui/chart-heat-gradient"
import { formatDate, money } from "@/lib/filters"
import type { Trip } from "@/lib/queries/trips"

const chartTooltip = <ChartTooltipContent formatter={(value) => money.format(Number(value))} />

function TripComparisonLegend() {
  return <div className="flex items-center justify-center gap-4 pt-3">
    <span className="flex items-center gap-1.5 text-sm"><span className="size-2.5 shrink-0 rounded-sm" style={{ background: COOL_GRADIENT_CSS }} />Per day</span>
    <span className="flex items-center gap-1.5 text-sm"><span className="size-2.5 shrink-0 rounded-sm" style={{ background: HEAT_GRADIENT_CSS }} />Total spend</span>
  </div>
}

export function TripComparisonChart({ trips }: { trips: Trip[] }) {
  const totalGradientId = useHeatGradientId()
  const dailyGradientId = useHeatGradientId()
  const data = trips.map((trip) => ({ name: trip.name, total: trip.total_spend, daily: trip.avg_per_day }))
  return <Card><CardHeader><CardTitle>Compare trips</CardTitle><CardDescription>Total and average spend per day</CardDescription></CardHeader><CardContent>
    <ChartContainer config={{ total: { label: "Total spend", color: "#1c69d4" }, daily: { label: "Per day", color: "#65778f" } }} className="h-72 w-full aspect-auto">
      <BarChart data={data} margin={{ left: 8, right: 8 }}><defs><ChartHeatGradient id={totalGradientId} /><ChartHeatGradient id={dailyGradientId} tone="cool" /></defs><CartesianGrid vertical={false} /><XAxis dataKey="name" tickLine={false} axisLine={false} tickFormatter={(name: string) => name.length > 16 ? `${name.slice(0, 15)}…` : name} /><YAxis yAxisId="total" tickFormatter={(value: number) => `${value} €`} tickLine={false} axisLine={false} width={60} /><YAxis yAxisId="daily" orientation="right" tickFormatter={(value: number) => `${value} €/d`} tickLine={false} axisLine={false} width={70} /><ChartTooltip content={chartTooltip} /><ChartLegend content={<TripComparisonLegend />} /><Bar yAxisId="total" dataKey="total" fill="#1c69d4" radius={0}>{data.map((row, index) => <Cell key={`${row.name}-${index}`} fill={`url(#${totalGradientId})`} />)}</Bar><Bar yAxisId="daily" dataKey="daily" fill="#65778f" radius={0}>{data.map((row, index) => <Cell key={`${row.name}-${index}`} fill={`url(#${dailyGradientId})`} />)}</Bar></BarChart>
    </ChartContainer>
  </CardContent></Card>
}

export function TripDailyChart({ data, outsideCount }: { data: { date: string; spend: number }[]; outsideCount: number }) {
  const heatGradientId = useHeatGradientId()
  return <Card><CardHeader><CardTitle>Daily spend</CardTitle><CardDescription>One bar for every day of the trip</CardDescription></CardHeader><CardContent>
    <ChartContainer config={{ spend: { label: "Spend", color: "#1c69d4" } }} className="h-72 w-full aspect-auto">
      <BarChart data={data}><defs><ChartHeatGradient id={heatGradientId} /></defs><CartesianGrid vertical={false} /><XAxis dataKey="date" tickFormatter={(date: string) => date.slice(8)} tickLine={false} axisLine={false} /><YAxis tickFormatter={(value: number) => `${value} €`} tickLine={false} axisLine={false} width={60} /><ChartTooltip content={<ChartTooltipContent labelFormatter={(value) => formatDate(String(value))} formatter={(value) => money.format(Number(value))} />} /><Bar dataKey="spend" fill={`url(#${heatGradientId})`} radius={0} /></BarChart>
    </ChartContainer>
    {outsideCount > 0 && <p className="mt-2 text-xs text-muted-foreground">{outsideCount.toLocaleString("de-DE")} manually added transaction{outsideCount === 1 ? "" : "s"} dated outside the trip are counted in totals but omitted here.</p>}
  </CardContent></Card>
}
