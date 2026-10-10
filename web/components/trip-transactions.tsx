"use client"

import { useRef, useState, useTransition, type FormEvent } from "react"
import { Plus, Search } from "lucide-react"
import { includeTransaction, resetTransaction } from "@/app/trips/actions"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet"
import { Badge } from "@/components/ui/badge"
import { formatDate, money } from "@/lib/filters"
import type { CandidateTransaction, ExcludedTransaction } from "@/lib/queries/trips"

export function AddTripTransactions({ tripId, initialFrom, initialTo }: { tripId: string; initialFrom: string; initialTo: string }) {
  const [open, setOpen] = useState(false)
  const [from, setFrom] = useState(initialFrom)
  const [to, setTo] = useState(initialTo)
  const [query, setQuery] = useState("")
  const request = useRef<AbortController | null>(null)
  const [rows, setRows] = useState<CandidateTransaction[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [adding, setAdding] = useState<string | null>(null)

  function loadCandidates(filters: { from: string; to: string; q: string }) {
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    const params = new URLSearchParams(filters)
    setLoading(true)
    setError("")
    fetch(`/trips/${tripId}/candidates?${params}`, { signal: controller.signal })
      .then((response) => { if (!response.ok) throw new Error("Could not search transactions."); return response.json() as Promise<CandidateTransaction[]> })
      .then((results) => setRows(results))
      .catch((cause) => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Could not search transactions.") })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
  }

  function search(event: FormEvent) {
    event.preventDefault()
    if (!from || !to || from > to) { setError("Choose a valid date range."); return }
    loadCandidates({ from, to, q: query.trim() })
  }
  async function add(id: string) {
    setAdding(id)
    setError("")
    try {
      await includeTransaction(tripId, id)
      setRows((current) => current.filter((row) => row.id !== id))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not add transaction.")
    } finally { setAdding(null) }
  }

  return <Sheet open={open} onOpenChange={(next) => { setOpen(next); if (next) loadCandidates({ from, to, q: query.trim() }); else request.current?.abort() }}>
    <SheetTrigger render={<Button variant="outline" /> }><Plus />Add transactions</SheetTrigger>
    <SheetContent className="sm:max-w-xl"><SheetHeader><SheetTitle>Add transactions</SheetTitle><SheetDescription>Find spend booked outside this trip’s dates, such as flights or hotels paid in advance. Results include all accounts and exclude Housing &amp; Utilities.</SheetDescription></SheetHeader>
      <div className="flex min-h-0 flex-1 flex-col gap-4 px-4 pb-4">
        <form onSubmit={search} className="space-y-3">
          <div className="grid grid-cols-2 gap-2"><label className="space-y-1 text-xs text-muted-foreground">From<input type="date" value={from} onChange={(event) => setFrom(event.target.value)} className="w-full rounded-lg border bg-background px-2 py-1.5 text-sm text-foreground" /></label><label className="space-y-1 text-xs text-muted-foreground">To<input type="date" value={to} onChange={(event) => setTo(event.target.value)} className="w-full rounded-lg border bg-background px-2 py-1.5 text-sm text-foreground" /></label></div>
          <div className="flex gap-2"><Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search merchant or description" aria-label="Search transactions to add" /><Button type="submit" variant="outline" aria-label="Search"><Search /></Button></div>
        </form>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <div className="min-h-0 flex-1 overflow-y-auto">
          {loading ? <p className="py-8 text-center text-sm text-muted-foreground">Searching…</p> : rows.length === 0 ? <p className="py-8 text-center text-sm text-muted-foreground">No matching transactions outside the trip dates.</p> : <div className="divide-y">{rows.map((row) => <div key={row.id} className="flex items-center gap-3 py-3 text-sm"><div className="min-w-0 flex-1"><div className="truncate font-medium">{row.merchant || row.counterparty_raw || "Unknown"}</div><div className="text-xs text-muted-foreground">{formatDate(row.date)} · {row.account_name} · {row.category || "Uncategorized"}</div></div><span className="shrink-0 tabular-nums">{money.format(-row.amount)}</span><Button type="button" variant="outline" size="sm" disabled={adding === row.id} onClick={() => add(row.id)}>{adding === row.id ? "Adding…" : "Add"}</Button></div>)}</div>}
        </div>
        {rows.length === 100 && <p className="text-xs text-muted-foreground">Showing the first 100 matches. Narrow your dates or search to find more.</p>}
      </div>
    </SheetContent>
  </Sheet>
}

export function ExcludedTripTransactions({ tripId, rows }: { tripId: string; rows: ExcludedTransaction[] }) {
  const [pending, startTransition] = useTransition()
  return <details className="rounded-xl border p-4"><summary className="cursor-pointer font-medium">Excluded transactions <Badge variant="secondary" className="ml-2">{rows.length.toLocaleString("de-DE")}</Badge></summary>
    <div className="mt-4 divide-y">{rows.length === 0 ? <p className="py-3 text-sm text-muted-foreground">Nothing has been excluded from this trip.</p> : rows.map((row) => <div key={row.id} className="flex flex-wrap items-center gap-3 py-3 text-sm"><span className="text-muted-foreground">{formatDate(row.date)}</span><span className="min-w-0 flex-1 font-medium">{row.merchant || row.counterparty_raw || "Unknown"}</span><span className="text-muted-foreground">{row.account_name}</span><span className="tabular-nums">{money.format(row.amount)}</span><Button variant="outline" size="sm" disabled={pending} onClick={() => startTransition(async () => { if (row.in_date_range) await resetTransaction(tripId, row.id); else await includeTransaction(tripId, row.id) })}>Restore</Button></div>)}</div>
  </details>
}
