"use client"

import { usePathname } from "next/navigation"
import { DateRangeSelect } from "@/components/date-range-select"

export function ContextDateRange() {
  const pathname = usePathname()
  return pathname.startsWith("/trips") ? null : <DateRangeSelect />
}
