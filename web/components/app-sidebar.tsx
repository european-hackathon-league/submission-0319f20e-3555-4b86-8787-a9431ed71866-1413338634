"use client"

import * as React from "react"
import Link from "next/link"
import Image from "next/image"
import {
  CalendarDays,
  LayoutDashboard,
  ListChecks,
  Plane,
  ReceiptText,
  Repeat,
  Settings,
  TrendingUp,
  ArrowUpRight,
} from "lucide-react"

import { AccountSwitcher } from "@/components/account-switcher"
import { NavMain } from "@/components/nav-main"
import { NavSecondary } from "@/components/nav-secondary"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarGroupLabel,
} from "@/components/ui/sidebar"

const mainItems = [
  { title: "Overview", url: "/", icon: LayoutDashboard },
  { title: "Transactions", url: "/transactions", icon: ReceiptText },
  { title: "Monthly", url: "/monthly", icon: CalendarDays },
  { title: "Subscriptions", url: "/recurring", icon: Repeat },
  { title: "Trips", url: "/trips", icon: Plane },
  { title: "Trends", url: "/trends", icon: TrendingUp },
]

const secondaryItems = [
  { title: "Review", url: "/review", icon: ListChecks },
  { title: "Settings", url: "/settings", icon: Settings },
]

export function AppSidebar({ lastSynced, ...props }: React.ComponentProps<typeof Sidebar> & { lastSynced: React.ReactNode }) {
  return (
    <Sidebar variant="sidebar" collapsible="icon" {...props}>
      <SidebarHeader>
        <Link href="/" className="brand-lockup" aria-label="BMW Finance home">
          <span className="brand-symbol"><Image src="/brand/bmw-white.svg" alt="BMW" width={38} height={38} priority /></span>
          <span className="brand-name">BMW<span className="brand-subtitle">Financial workspace</span></span>
        </Link>
        <div className="account-switcher-wrap">
        <AccountSwitcher />
        </div>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroupLabel>Workspace</SidebarGroupLabel>
        <NavMain items={mainItems} />
        <NavSecondary items={secondaryItems} className="mt-auto" />
      </SidebarContent>
      <SidebarFooter>
        {lastSynced}
        <Link href="/settings" className="workspace-profile" aria-label="Workspace settings">
          <span className="profile-monogram" aria-hidden="true">B</span>
          <span className="profile-label"><strong>Personal workspace</strong><span>BMW concept</span></span>
          <ArrowUpRight className="profile-arrow size-4" />
        </Link>
      </SidebarFooter>
    </Sidebar>
  )
}
