import Link from "next/link"
import { notFound } from "next/navigation"
import { ArrowLeft, MapPin } from "lucide-react"
import { CategoryDonut, HorizontalSpendChart } from "@/components/dashboard-charts"
import { DataTable } from "@/components/data-table"
import { SectionCards } from "@/components/section-cards"
import { TripDailyChart } from "@/components/trip-charts"
import { TripFormDialog, DeleteTripDialog } from "@/components/trip-management"
import { AddTripTransactions, ExcludedTripTransactions } from "@/components/trip-transactions"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { formatDate, globalFilterQuery, money } from "@/lib/filters"
import type { Params } from "@/lib/filters"
import { transactionOptions } from "@/lib/queries/transactions"
import { defaultCandidateRange, getExcludedTransactions, getTrip, getTripAnalytics, getTripTransactions } from "@/lib/queries/trips"

export const dynamic = "force-dynamic"

export default async function TripPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<Params> }) {
  const [{ id }, query] = await Promise.all([params, searchParams])
  if (!/^[1-9]\d{0,18}$/.test(id)) notFound()
  const trip = await getTrip(id)
  if (!trip) notFound()
  const options = transactionOptions(query)
  const [analytics, transactions, excluded] = await Promise.all([
    getTripAnalytics(id), getTripTransactions(id, options), getExcludedTransactions(id),
  ])
  const candidateRange = defaultCandidateRange(trip)
  const retained = globalFilterQuery(query)
  return <main className="space-y-5">
    <div><Link href={`/trips${retained ? `?${retained}` : ""}`} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" />All trips</Link></div>
    <div className="flex flex-wrap items-start justify-between gap-3"><div><h1 className="text-2xl font-semibold tracking-tight">{trip.name}</h1>{trip.destination && <p className="mt-1 flex items-center gap-1 text-sm text-muted-foreground"><MapPin className="size-4" />{trip.destination}</p>}<p className="mt-1 text-sm text-muted-foreground">{formatDate(trip.start_date)} – {formatDate(trip.end_date)} · {trip.days} {trip.days === 1 ? "day" : "days"} · all accounts</p></div><div className="flex items-center gap-2"><TripFormDialog trip={trip} trigger={<Button variant="outline">Edit</Button>} /><DeleteTripDialog trip={trip} trigger={<Button variant="destructive">Delete</Button>} /></div></div>
    {trip.notes && <p className="rounded-lg border bg-muted/30 p-3 text-sm">{trip.notes}</p>}
    <SectionCards metrics={[{ label: "Total spend", value: trip.total_spend }, { label: "Per day", value: trip.avg_per_day }, { label: "Transactions", value: trip.txn_count, format: "count" }, { label: "Cash withdrawn", value: trip.cash }, { label: "Fees (FX + ATM)", value: trip.fees }]} />
    <div className="grid gap-4 lg:grid-cols-2"><TripDailyChart data={analytics.daily} outsideCount={analytics.outsideCount} />{analytics.categories.length ? <CategoryDonut data={analytics.categories} /> : <Card><CardHeader><CardTitle>Spend by category</CardTitle></CardHeader><CardContent className="flex h-64 items-center justify-center text-sm text-muted-foreground">No spending in this trip.</CardContent></Card>}</div>
    <div className="grid gap-4 lg:grid-cols-2"><HorizontalSpendChart title="Top merchants" description="Ten merchants with the highest spend" data={analytics.merchants} /><Card><CardHeader><CardTitle>Spend by account</CardTitle></CardHeader><CardContent>{analytics.accounts.length ? <div className="space-y-4">{analytics.accounts.map((row) => <div key={row.account} className="space-y-1.5"><div className="flex justify-between text-sm"><span>{row.account}</span><strong className="tabular-nums">{money.format(row.spend)}</strong></div><div className="h-2 rounded-none bg-muted"><div className="h-full rounded-none bg-chart-2" style={{ width: `${Math.max(0, Math.min(100, trip.total_spend ? (row.spend / trip.total_spend) * 100 : 0))}%` }} /></div></div>)}</div> : <p className="py-12 text-center text-sm text-muted-foreground">No account spending in this trip.</p>}</CardContent></Card></div>
    <section className="space-y-4"><div className="flex flex-wrap items-center justify-between gap-2"><div><h2 className="text-lg font-semibold">Transactions</h2><p className="text-sm text-muted-foreground">Search, inspect, and adjust the transactions included in this trip.</p></div><AddTripTransactions tripId={id} initialFrom={candidateRange.from} initialTo={candidateRange.to} /></div><DataTable {...transactions} options={options} tripId={id} /></section>
    <ExcludedTripTransactions tripId={id} rows={excluded} />
  </main>
}
