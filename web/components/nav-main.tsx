"use client"

import { Suspense } from "react"
import Link from "next/link"
import { usePathname, useSearchParams } from "next/navigation"
import type { LucideIcon } from "lucide-react"

import {
  SidebarGroup,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar"

function NavMainLinks({
  items,
}: {
  items: { title: string; url: string; icon: LucideIcon }[]
}) {
  const { isMobile, setOpenMobile } = useSidebar()
  const pathname = usePathname()
  const search = useSearchParams()
  const retained = new URLSearchParams()
  for (const key of ["account", "from", "to", "range"]) {
    const value = search.get(key)
    if (value) retained.set(key, value)
  }

  return (
    <SidebarGroup>
      <SidebarMenu>
        {items.map((item) => {
          const Icon = item.icon
          const query = retained.toString()

          return (
            <SidebarMenuItem key={item.title}>
              <SidebarMenuButton
                onClick={() => { if (isMobile) setOpenMobile(false) }}
                tooltip={item.title}
                isActive={pathname === item.url || (item.url === "/trips" && pathname.startsWith("/trips/"))}
                render={<Link href={`${item.url}${query ? `?${query}` : ""}`} />}
              >
                <Icon />
                <span>{item.title}</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          )
        })}
      </SidebarMenu>
    </SidebarGroup>
  )
}

export function NavMain(props: { items: { title: string; url: string; icon: LucideIcon }[] }) {
  return <Suspense fallback={null}><NavMainLinks {...props} /></Suspense>
}
