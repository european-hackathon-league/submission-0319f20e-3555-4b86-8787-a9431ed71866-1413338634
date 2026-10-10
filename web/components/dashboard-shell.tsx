import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { MotionField } from "@/components/motion-field"
import { ScanLine } from "lucide-react"

export function PageHeading({ title, description, action }: { title: string; description: string; action?: React.ReactNode }) {
  if (title === "Overview") return <>
    <section className="overview-intro" aria-labelledby="overview-title">
      <MotionField />
      <div className="overview-intro-copy"><p className="overview-eyebrow">Precision in every detail</p><h1 id="overview-title">Overview</h1><p className="overview-description">{description}</p></div>
    </section>
    <div className="overview-toolbar"><h2>Account performance</h2>{action}</div>
  </>
  return <div className="page-heading"><div><h1>{title}</h1><p>{description}</p></div>{action && <div className="page-heading-action">{action}</div>}</div>
}

export function EmptyState({ title = "No data for this selection", description = "Try another account or date range." }: { title?: string; description?: string }) {
  return <Card><CardContent className="flex min-h-64 flex-col items-center justify-center text-center"><ScanLine className="mb-5 size-7 text-muted-foreground" strokeWidth={1} /><h2 className="font-medium">{title}</h2><p className="mt-2 text-sm text-muted-foreground">{description}</p></CardContent></Card>
}

export function DashboardLoading({ cards = 4, charts = 2 }: { cards?: number; charts?: number }) {
  return <div className="space-y-4"><Skeleton className="h-8 w-48" /><div className={`grid gap-4 sm:grid-cols-2 ${cards === 3 ? "xl:grid-cols-3" : "xl:grid-cols-4"}`}>{Array.from({ length: cards }, (_, i) => <Skeleton key={i} className="h-28 rounded-xl" />)}</div><div className="grid gap-4 lg:grid-cols-2">{Array.from({ length: charts }, (_, i) => <Skeleton key={i} className="h-80 rounded-xl" />)}</div></div>
}
