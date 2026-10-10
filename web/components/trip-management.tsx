"use client"

import { useState, useTransition, type FormEvent, type ReactElement } from "react"
import { useRouter } from "next/navigation"
import { CalendarDays, MoreHorizontal, Plus } from "lucide-react"
import { createTrip, deleteTrip, updateTrip } from "@/app/trips/actions"
import { formatDate } from "@/lib/filters"
import type { Trip } from "@/lib/queries/trips"
import { Button } from "@/components/ui/button"
import { Calendar } from "@/components/ui/calendar"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from "@/components/ui/alert-dialog"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"

function localDate(iso: string) { return new Date(`${iso}T12:00:00`) }
function isoDate(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`
}
function currentGlobalQuery() {
  const source = new URLSearchParams(window.location.search)
  const retained = new URLSearchParams()
  for (const key of ["account", "from", "to", "range"]) {
    const value = source.get(key)
    if (value) retained.set(key, value)
  }
  const query = retained.toString()
  return query ? `?${query}` : ""
}

export function TripFormDialog({ trip, trigger }: { trip?: Trip; trigger?: ReactElement }) {
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [pending, startTransition] = useTransition()
  const [name, setName] = useState(trip?.name ?? "")
  const [destination, setDestination] = useState(trip?.destination ?? "")
  const [notes, setNotes] = useState(trip?.notes ?? "")
  const [from, setFrom] = useState(trip?.start_date ?? "")
  const [to, setTo] = useState(trip?.end_date ?? "")
  const [error, setError] = useState("")
  const [calendarOpen, setCalendarOpen] = useState(false)

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!from || !to) { setError("Choose a start and end date."); return }
    setError("")
    startTransition(async () => {
      try {
        const input = { name, destination, notes, start_date: from, end_date: to }
        if (trip) await updateTrip(trip.id, input)
        else {
          const id = await createTrip(input)
          router.push(`/trips/${id}${currentGlobalQuery()}`)
        }
        setOpen(false)
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "Could not save this trip.")
      }
    })
  }

  return <Dialog open={open} onOpenChange={setOpen}>
    {trigger ? <DialogTrigger render={trigger} /> : <DialogTrigger render={<Button />}><Plus />New trip</DialogTrigger>}
    <DialogContent className="sm:max-w-lg">
      <DialogHeader><DialogTitle>{trip ? "Edit trip" : "New trip"}</DialogTitle><DialogDescription>Spending during these dates appears automatically across all accounts, except Housing &amp; Utilities.</DialogDescription></DialogHeader>
      <form onSubmit={submit} className="space-y-4">
        <div className="space-y-2"><Label htmlFor={`trip-name-${trip?.id ?? "new"}`}>Name</Label><Input id={`trip-name-${trip?.id ?? "new"}`} required maxLength={120} value={name} onChange={(event) => setName(event.target.value)} placeholder="New York" /></div>
        <div className="space-y-2"><Label htmlFor={`trip-destination-${trip?.id ?? "new"}`}>Destination</Label><Input id={`trip-destination-${trip?.id ?? "new"}`} maxLength={120} value={destination} onChange={(event) => setDestination(event.target.value)} placeholder="New York, USA" /></div>
        <div className="space-y-2"><Label>Date range</Label>
          <Popover open={calendarOpen} onOpenChange={setCalendarOpen}>
            <PopoverTrigger render={<Button type="button" variant="outline" className="w-full justify-start font-normal" />}>
              <CalendarDays />{from && to ? `${formatDate(from)} – ${formatDate(to)}` : "Choose dates"}
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0" align="start">
              <Calendar mode="range" selected={{ from: from ? localDate(from) : undefined, to: to ? localDate(to) : undefined }}
                onSelect={(range) => { setFrom(range?.from ? isoDate(range.from) : ""); setTo(range?.to ? isoDate(range.to) : "") }}
                defaultMonth={from ? localDate(from) : undefined} numberOfMonths={1} />
              <div className="flex justify-end border-t p-2"><Button type="button" variant="ghost" size="sm" onClick={() => setCalendarOpen(false)}>Done</Button></div>
            </PopoverContent>
          </Popover>
        </div>
        <div className="space-y-2"><Label htmlFor={`trip-notes-${trip?.id ?? "new"}`}>Notes</Label><textarea id={`trip-notes-${trip?.id ?? "new"}`} maxLength={5000} value={notes} onChange={(event) => setNotes(event.target.value)} rows={3} className="w-full rounded-lg border bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring" placeholder="Optional notes" /></div>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <DialogFooter><Button type="submit" disabled={pending}>{pending ? "Saving…" : trip ? "Save changes" : "Create trip"}</Button></DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
}

export function DeleteTripDialog({ trip, trigger }: { trip: Trip; trigger: ReactElement }) {
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [pending, startTransition] = useTransition()
  const [error, setError] = useState("")
  return <AlertDialog open={open} onOpenChange={setOpen}>
    <AlertDialogTrigger render={trigger} />
    <AlertDialogContent><AlertDialogHeader><AlertDialogTitle>Delete {trip.name}?</AlertDialogTitle><AlertDialogDescription>The trip and its manual transaction choices will be removed. Your transactions stay in the dashboard.</AlertDialogDescription></AlertDialogHeader>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction variant="destructive" disabled={pending} onClick={() => startTransition(async () => { try { await deleteTrip(trip.id); setOpen(false); router.push(`/trips${currentGlobalQuery()}`) } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not delete trip.") } })}>{pending ? "Deleting…" : "Delete trip"}</AlertDialogAction></AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
}

export function TripCardMenu({ trip }: { trip: Trip }) {
  const [menuOpen, setMenuOpen] = useState(false)
  return <div className="relative z-10 flex items-start gap-1">
    <DropdownMenu open={menuOpen} onOpenChange={setMenuOpen}>
      <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" aria-label={`Actions for ${trip.name}`} />}><MoreHorizontal /></DropdownMenuTrigger>
      <DropdownMenuContent align="end"><DropdownMenuItem onClick={() => { setMenuOpen(false); document.getElementById(`edit-trip-${trip.id}`)?.click() }}>Edit</DropdownMenuItem><DropdownMenuItem variant="destructive" onClick={() => { setMenuOpen(false); document.getElementById(`delete-trip-${trip.id}`)?.click() }}>Delete</DropdownMenuItem></DropdownMenuContent>
    </DropdownMenu>
    <span className="sr-only"><TripFormDialog trip={trip} trigger={<button id={`edit-trip-${trip.id}`} type="button">Edit</button>} /><DeleteTripDialog trip={trip} trigger={<button id={`delete-trip-${trip.id}`} type="button">Delete</button>} /></span>
  </div>
}
