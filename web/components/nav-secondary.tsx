"use client"

import * as React from "react"
import { Suspense } from "react"
import Link from "next/link"
import { usePathname, useSearchParams } from "next/navigation"
import type { LucideIcon } from "lucide-react"

import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar"

function NavSecondaryLinks({
  items,
  ...props
}: {
  items: { title: string; url: string; icon: LucideIcon }[]
} & React.ComponentPropsWithoutRef<typeof SidebarGroup>) {
  const { isMobile, setOpenMobile } = useSidebar()
  const pathname = usePathname()
  const search = useSearchParams()
  const retained = new URLSearchParams()
  for (const key of ["account", "from", "to", "range"]) {
    const value = search.get(key)
    if (value) retained.set(key, value)
  }

  return (
    <SidebarGroup {...props}>
      <SidebarGroupContent>
        <SidebarMenu>
          {items.map((item) => {
            const Icon = item.icon

            return (
              <SidebarMenuItem key={item.title}>
                <SidebarMenuButton
                  size="sm"
                  onClick={() => { if (isMobile) setOpenMobile(false) }}
                  tooltip={item.title}
                  isActive={pathname === item.url}
                  render={<Link href={`${item.url}${retained.size ? `?${retained}` : ""}`} />}
                >
                  <Icon />
                  <span>{item.title}</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            )
          })}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  )
}

export function NavSecondary(props: { items: { title: string; url: string; icon: LucideIcon }[] } & React.ComponentPropsWithoutRef<typeof SidebarGroup>) {
  return <Suspense fallback={null}><NavSecondaryLinks {...props} /></Suspense>
}
