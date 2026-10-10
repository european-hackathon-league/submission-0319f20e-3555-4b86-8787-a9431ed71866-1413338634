import { Suspense } from "react"
import type { Metadata } from "next"
import { Barlow, IBM_Plex_Mono } from "next/font/google"

import { AppSidebar } from "@/components/app-sidebar"
import { LastSynced } from "@/components/last-synced"
import { PageBreadcrumb } from "@/components/page-breadcrumb"
import { ContextDateRange } from "@/components/context-date-range"
import { AppearanceProvider, AppearanceToggle } from "@/components/appearance"
import { WorkspaceStatus } from "@/components/workspace-status"
import { Separator } from "@/components/ui/separator"
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import { TooltipProvider } from "@/components/ui/tooltip"

import "./globals.css"

const barlow = Barlow({
  variable: "--font-barlow",
  weight: ["300", "400", "500", "600"],
  subsets: ["latin"],
  display: "swap",
})

const plexMono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  weight: ["400", "500"],
  subsets: ["latin"],
})

export const metadata: Metadata = {
  title: "BMW | Financial Workspace",
  icons: { icon: "/brand/bmw-grey.svg" },
  description: "A BMW-inspired concept. A precise view of your accounts, spending, and financial patterns.",
}

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${barlow.variable} ${plexMono.variable} antialiased`}
    >
      <body>
        <AppearanceProvider>
        <a href="#workspace-content" className="skip-link">Skip to content</a>
        <TooltipProvider>
          <SidebarProvider style={{ "--sidebar-width": "15rem" } as React.CSSProperties}>
            <AppSidebar lastSynced={<Suspense fallback={null}><LastSynced /></Suspense>} />
            <SidebarInset>
              <header className="workspace-header">
                <div className="flex items-center gap-2">
                  <SidebarTrigger className="-ml-1" />
                  <Separator
                    orientation="vertical"
                    className="mr-2 data-vertical:h-4 data-vertical:self-auto"
                  />
                  <PageBreadcrumb />
                </div>
                <div className="flex min-w-0 items-center gap-3">
                  <Suspense fallback={null}><WorkspaceStatus /></Suspense>
                  <ContextDateRange />
                  <AppearanceToggle />
                </div>
              </header>
              <div id="workspace-content" tabIndex={-1} className="workspace-content">
                {children}
              </div>
            </SidebarInset>
          </SidebarProvider>
        </TooltipProvider>
        </AppearanceProvider>
      </body>
    </html>
  )
}
