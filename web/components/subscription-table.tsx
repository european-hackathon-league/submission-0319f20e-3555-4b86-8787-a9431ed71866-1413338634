import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { formatDate, money } from "@/lib/filters"
import type { Subscription } from "@/lib/queries/types"

const cadenceLabels: Record<string, string> = {
  weekly: "week",
  monthly: "month",
  quarterly: "quarter",
  yearly: "year",
}

const statusLabels: Record<Subscription["status"], string> = {
  active: "Active",
  paused: "Paused",
  cancelled: "Cancelled",
}

export function SubscriptionTable({ rows }: { rows: Subscription[] }) {
  return <Card>
    <CardHeader>
      <CardTitle>Subscriptions</CardTitle>
      <CardDescription>Yearly cost is annualized from each listed price. Paused plans show a benchmark and are excluded from current totals.</CardDescription>
    </CardHeader>
    <CardContent><Table>
      <TableHeader><TableRow>
        <TableHead>Subscription</TableHead>
        <TableHead>Category</TableHead>
        <TableHead>Billing</TableHead>
        <TableHead className="text-right">Price</TableHead>
        <TableHead className="text-right">Yearly cost</TableHead>
        <TableHead>Last payment</TableHead>
        <TableHead>Status</TableHead>
      </TableRow></TableHeader>
      <TableBody>{rows.map((row) => (
        <TableRow key={row.id}>
          <TableCell className="font-medium">
            <div>{row.name}</div>
            {row.notes && <div className="mt-0.5 text-xs font-normal text-muted-foreground">{row.notes}</div>}
          </TableCell>
          <TableCell>{row.parent_category ? `${row.parent_category} / ` : ""}{row.category ?? "Uncategorized"}</TableCell>
          <TableCell><Badge variant="outline" className="capitalize">{row.cadence}</Badge></TableCell>
          <TableCell className="text-right tabular-nums">{money.format(row.amount)} / {cadenceLabels[row.cadence] ?? row.cadence}</TableCell>
          <TableCell className="text-right tabular-nums">{row.yearly_cost == null ? "—" : money.format(row.yearly_cost)}</TableCell>
          <TableCell>{formatDate(row.last_charge)}</TableCell>
          <TableCell><Badge variant={row.status === "active" ? "secondary" : "outline"}>{statusLabels[row.status]}</Badge></TableCell>
        </TableRow>
      ))}</TableBody>
    </Table></CardContent>
  </Card>
}
