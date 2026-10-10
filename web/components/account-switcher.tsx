"use client"

import { Suspense } from "react"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { Building2, ChevronsUpDown, Landmark, Wallet } from "lucide-react"

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar"

const accounts = [
  { name: "All accounts", value: null, icon: Wallet },
  { name: "Sparkasse", value: "sparkasse_giro", icon: Landmark },
  { name: "Revolut", value: "revolut_eur", icon: Building2 },
] as const

function AccountSwitcherMenu() {
  const { isMobile } = useSidebar()
  const pathname = usePathname()
  const router = useRouter()
  const searchParams = useSearchParams()
  const activeAccount =
    accounts.find((account) => account.value === searchParams.get("account")) ??
    accounts[0]
  const ActiveIcon = activeAccount.icon

  function selectAccount(value: (typeof accounts)[number]["value"]) {
    const params = new URLSearchParams(searchParams.toString())
    params.delete("page")

    if (value) {
      params.set("account", value)
    } else {
      params.delete("account")
    }

    const query = params.toString()
    router.push(`${pathname}${query ? `?${query}` : ""}`, { scroll: false })
  }

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <SidebarMenuButton
                size="lg"
                className="data-open:bg-sidebar-accent data-open:text-sidebar-accent-foreground"
                aria-label={`Account filter: ${activeAccount.name}`}
              />
            }
          >
            <div className="account-icon flex aspect-square size-8 items-center justify-center">
              <ActiveIcon className="size-4" />
            </div>
            <div className="grid flex-1 text-left text-sm leading-tight">
              <span className="truncate font-medium">{activeAccount.name}</span>
              <span className="truncate text-xs text-sidebar-foreground/60">Account selection</span>
            </div>
            <ChevronsUpDown className="ml-auto" />
          </DropdownMenuTrigger>
          <DropdownMenuContent
            className="w-fit"
            align="start"
            side={isMobile ? "bottom" : "right"}
            sideOffset={4}
          >
            <DropdownMenuGroup>
              <DropdownMenuLabel className="text-xs text-muted-foreground">
                Accounts
              </DropdownMenuLabel>
              {accounts.map((account) => {
                const Icon = account.icon

                return (
                  <DropdownMenuItem
                    key={account.name}
                    onClick={() => selectAccount(account.value)}
                    className="gap-2 p-2"
                  >
                    <div className="flex size-6 items-center justify-center rounded-md border">
                      <Icon className="size-4" />
                    </div>
                    {account.name}
                  </DropdownMenuItem>
                )
              })}
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}

export function AccountSwitcher() {
  return (
    <Suspense fallback={<div className="h-12" />}>
      <AccountSwitcherMenu />
    </Suspense>
  )
}
