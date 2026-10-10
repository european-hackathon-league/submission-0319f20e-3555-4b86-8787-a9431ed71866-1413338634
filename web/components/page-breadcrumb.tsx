"use client"

import { usePathname } from "next/navigation"

import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
} from "@/components/ui/breadcrumb"

const pageTitles: Record<string, string> = {
  "/": "Overview",
  "/transactions": "Transactions",
  "/monthly": "Monthly",
  "/recurring": "Subscriptions",
  "/trips": "Trips",
  "/trends": "Trends",
  "/review": "Review",
  "/settings": "Settings",
}

export function PageBreadcrumb() {
  const pathname = usePathname()

  return (
    <Breadcrumb>
      <BreadcrumbList>
        <BreadcrumbItem>
          <BreadcrumbPage>{pathname.startsWith("/trips/") ? "Trip details" : pageTitles[pathname] ?? "Page"}</BreadcrumbPage>
        </BreadcrumbItem>
      </BreadcrumbList>
    </Breadcrumb>
  )
}
