"use client"

import { useMemo, useState } from "react"
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart"
import { ChartHeatGradient, useHeatGradientId } from "@/components/ui/chart-heat-gradient"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { formatDate, money, shiftDate } from "@/lib/filters"
import type { Daily } from "@/lib/queries/types"

export function ChartAreaInteractive({ data, from, to }: { data: Daily[]; from: string | null; to: string | null }) {
  const heatGradientId = useHeatGradientId()
  const [timeWindow, setTimeWindow] = useState("90")
  const points = useMemo(() => {
    const first = from ?? data[0]?.date
    const last = to ?? data.at(-1)?.date
    if (!first || !last) return []
    const byDate = new Map(data.map((row) => [row.date, row.spend]))
    const result: Daily[] = []
    const cutoff = timeWindow === "max" ? first : shiftDate(last, 1 - Number(timeWindow))
    for (let day = first < cutoff ? cutoff : first; day <= last; day = shiftDate(day, 1)) {
      result.push({ date: day, spend: byDate.get(day) ?? 0 })
    }
    return result
  }, [data, from, to, timeWindow])
  return <Card>
    <CardHeader>
      <CardTitle>Spend over time</CardTitle>
      <CardDescription>Money paid out each day; incoming money is excluded</CardDescription>
      <CardAction><ToggleGroup value={[timeWindow]} onValueChange={(values) => {
        if (values[0]) setTimeWindow(values[0])
      }} variant="outline" size="sm" spacing={0} aria-label="Chart time window">
        {[7, 30, 90].map((days) => <ToggleGroupItem key={days} value={String(days)}>{days}d</ToggleGroupItem>)}
        <ToggleGroupItem value="max" aria-label="Max: entire selected date range">Max</ToggleGroupItem>
      </ToggleGroup></CardAction>
    </CardHeader>
    <CardContent>
      <ChartContainer config={{ spend: { label: "Spend", color: "#1c69d4" } }} className="h-72 w-full aspect-auto">
        <AreaChart data={points} margin={{ left: 0, right: 10 }}>
          <defs>
            <ChartHeatGradient id={heatGradientId} />
          </defs>
          <CartesianGrid vertical={false} />
          <XAxis dataKey="date" tickLine={false} axisLine={false} minTickGap={24} tickFormatter={formatDate} />
          <YAxis domain={[0, "auto"]} tickLine={false} axisLine={false} tickFormatter={(value: number) => `${value} €`} width={55} />
          <ChartTooltip content={<ChartTooltipContent labelFormatter={(value) => formatDate(String(value))} formatter={(value) => <span className="font-mono tabular-nums">{money.format(Number(value))}</span>} />} />
          <Area dataKey="spend" type="monotone" stroke="var(--chart-accent)" fill={`url(#${heatGradientId})`} fillOpacity={0.18} strokeWidth={2} />
        </AreaChart>
      </ChartContainer>
    </CardContent>
  </Card>
}
