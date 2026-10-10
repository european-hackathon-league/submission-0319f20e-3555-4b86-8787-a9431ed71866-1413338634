import Link from "next/link"
import { MapPin } from "lucide-react"
import { PageHeading } from "@/components/dashboard-shell"
import { TripComparisonChart } from "@/components/trip-charts"
import { TripCardMenu, TripFormDialog } from "@/components/trip-management"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { formatDate, globalFilterQuery, money, type Params } from "@/lib/filters"
import { getTrips } from "@/lib/queries/trips"

export const dynamic = "force-dynamic"

export default async function TripsPage({ searchParams }: { searchParams: Promise<Params> }) {
  const retained = globalFilterQuery(await searchParams)
  const trips = await getTrips()
  return <main className="space-y-5">
    <PageHeading title="Trips" description="See every trip’s spending across all accounts." action={<TripFormDialog />} />
    {trips.length === 0 ? <Card><CardContent className="flex min-h-64 flex-col items-center justify-center gap-3 text-center"><h2 className="text-lg font-medium">No trips yet</h2><p className="max-w-md text-sm text-muted-foreground">Create a trip with its travel dates. Spending during that period appears automatically, and you can add or remove individual transactions.</p><TripFormDialog /></CardContent></Card> : <>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {trips.map((trip) => <Card key={trip.id} className="relative transition-colors hover:bg-muted/30">
          <CardHeader className="grid grid-cols-[1fr_auto] gap-2"><div className="min-w-0"><CardTitle className="truncate text-lg"><Link href={`/trips/${trip.id}${retained ? `?${retained}` : ""}`} className="after:absolute after:inset-0 focus-visible:underline">{trip.name}</Link></CardTitle>{trip.destination && <p className="mt-1 flex items-center gap-1 text-sm text-muted-foreground"><MapPin className="size-3.5" />{trip.destination}</p>}</div><TripCardMenu trip={trip} /></CardHeader>
          <CardContent className="space-y-4"><p className="text-sm text-muted-foreground">{formatDate(trip.start_date)} – {formatDate(trip.end_date)} · {trip.days} {trip.days === 1 ? "day" : "days"}</p><div className="grid grid-cols-2 gap-3 border-t pt-4"><div><p className="text-xs text-muted-foreground">Total spend</p><p className="text-xl font-semibold tabular-nums">{money.format(trip.total_spend)}</p></div><div><p className="text-xs text-muted-foreground">Per day</p><p className="text-xl font-semibold tabular-nums">{money.format(trip.avg_per_day)}</p></div></div></CardContent>
        </Card>)}
      </div>
      {trips.length >= 2 && <TripComparisonChart trips={trips} />}
    </>}
  </main>
}
