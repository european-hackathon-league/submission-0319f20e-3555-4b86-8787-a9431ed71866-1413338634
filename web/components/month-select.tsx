"use client"

import { Suspense } from "react"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { monthStart, today } from "@/lib/filters"

const monthFormatter = new Intl.DateTimeFormat("en-US", { month: "long", year: "numeric", timeZone: "UTC" })
function monthLabel(value: string) { return monthFormatter.format(new Date(`${value}-01T12:00:00Z`)) }

function Control({ month, months }: { month: string; months: string[] }) {
  const search = useSearchParams()
  const pathname = usePathname()
  const router = useRouter()
  const options = [...new Set([monthStart(today()).slice(0, 7), month, ...months])].sort().reverse()
  return <Select value={month} onValueChange={(value) => {
    if (!value) return
    const params = new URLSearchParams(search.toString())
    params.set("month", value); params.delete("page")
    router.push(`${pathname}?${params.toString()}`, { scroll: false })
  }}><SelectTrigger aria-label="Month"><SelectValue>{monthLabel(month)}</SelectValue></SelectTrigger><SelectContent>{options.map((value) => <SelectItem key={value} value={value}>{monthLabel(value)}</SelectItem>)}</SelectContent></Select>
}

export function MonthSelect({ month, months }: { month: string; months: string[] }) { return <Suspense fallback={null}><Control month={month} months={months} /></Suspense> }
