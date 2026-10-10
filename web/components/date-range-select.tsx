"use client"

import { Suspense, useState } from "react"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import type { DateRange } from "react-day-picker"
import { Button } from "@/components/ui/button"
import { Calendar } from "@/components/ui/calendar"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { ALL_TIME_URL, formatDate, presetRange, today } from "@/lib/filters"

const presets = [
  ["this", "This month"], ["last", "Last month"], ["3m", "Last 3 months"],
  ["6m", "Last 6 months"], ["12m", "Last 12 months"], ["all", "All time"],
] as const

function localDate(value: string | null | undefined): Date | undefined {
  if (!value || value < "1900-01-01" || value > "2100-12-31" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return undefined
  const [year, month, day] = value.split("-").map(Number)
  const date = new Date(year, month - 1, day, 12)
  return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day ? date : undefined
}

function isoDate(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`
}

function DateRangeControl() {
  const pathname = usePathname()
  const router = useRouter()
  const search = useSearchParams()
  const [calendarOpen, setCalendarOpen] = useState(false)
  const [draftRange, setDraftRange] = useState<DateRange | undefined>()
  if (["/monthly", "/recurring", "/review", "/settings"].includes(pathname)) return null

  const defaultPreset = pathname === "/trends" ? "12m" : "6m"
  const active = search.get("range") === "all" || (search.get("from") === ALL_TIME_URL.from && search.get("to") === ALL_TIME_URL.to) ? "all" : !search.has("from") || !search.has("to")
    ? defaultPreset
    : presets.find(([key]) => {
      const range = presetRange(key)
      return range.from === search.get("from") && range.to === search.get("to")
    })?.[0] ?? "custom"
  const selectedValue = calendarOpen ? "custom" : active
  const activeLabel = presets.find(([key]) => key === selectedValue)?.[1] ?? "Custom range"

  function startCustomSelection() {
    if (active === "custom") {
      const from = localDate(search.get("from"))
      const to = localDate(search.get("to"))
      setDraftRange(from && to ? { from, to } : undefined)
    } else if (active !== "all") {
      const range = presetRange(active)
      const from = localDate(range.from)
      const to = localDate(range.to)
      setDraftRange(from && to ? { from, to } : undefined)
    } else {
      setDraftRange(undefined)
    }
    setCalendarOpen(true)
  }

  function change(value: string | null) {
    if (!value) return
    if (value === "custom") {
      startCustomSelection()
      return
    }
    const params = new URLSearchParams(search.toString())
    params.delete("page")
    if (value === "all") {
      params.delete("range")
      params.set("from", ALL_TIME_URL.from)
      params.set("to", ALL_TIME_URL.to)
    } else {
      const range = presetRange(value)
      params.delete("range")
      params.set("from", range.from!)
      params.set("to", range.to!)
    }
    router.push(`${pathname}?${params.toString()}`, { scroll: false })
  }

  function applyCustomRange() {
    if (!draftRange?.from || !draftRange.to) return
    const params = new URLSearchParams(search.toString())
    params.delete("page")
    params.delete("range")
    params.set("from", isoDate(draftRange.from))
    params.set("to", isoDate(draftRange.to))
    router.push(`${pathname}?${params.toString()}`, { scroll: false })
    setCalendarOpen(false)
  }

  return <>
    <Select value={selectedValue} onValueChange={change}>
      <SelectTrigger size="sm" aria-label="Date range"><SelectValue>{activeLabel}</SelectValue></SelectTrigger>
      <SelectContent>
        {presets.map(([key, label]) => <SelectItem key={key} value={key}>{label}</SelectItem>)}
        <SelectItem value="custom">Custom range</SelectItem>
      </SelectContent>
    </Select>
    <Dialog open={calendarOpen} onOpenChange={setCalendarOpen}>
      <DialogContent className="sm:max-w-fit">
        <DialogHeader>
          <DialogTitle>Choose a custom range</DialogTitle>
          <DialogDescription>Select a start and end date.</DialogDescription>
        </DialogHeader>
        <Calendar
          mode="range"
          selected={draftRange}
          onSelect={setDraftRange}
          defaultMonth={draftRange?.from ?? localDate(today())}
          disabled={{ before: new Date(1900, 0, 1), after: new Date(2100, 11, 31) }}
          numberOfMonths={2}
        />
        <DialogFooter>
          <p className="mr-auto self-center text-sm text-muted-foreground">
            {draftRange?.from && draftRange.to
              ? `${formatDate(isoDate(draftRange.from))} – ${formatDate(isoDate(draftRange.to))}`
              : "Choose both dates"}
          </p>
          <Button type="button" variant="outline" onClick={() => setCalendarOpen(false)}>Cancel</Button>
          <Button type="button" disabled={!draftRange?.from || !draftRange.to} onClick={applyCustomRange}>Apply</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </>
}

export function DateRangeSelect() { return <Suspense fallback={null}><DateRangeControl /></Suspense> }
