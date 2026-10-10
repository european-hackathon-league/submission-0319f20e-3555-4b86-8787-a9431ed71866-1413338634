"use client"

import { ThemeProvider, useTheme } from "next-themes"
import { Moon, Sun } from "lucide-react"
import { Button } from "@/components/ui/button"

export function AppearanceProvider({ children }: { children: React.ReactNode }) {
  return <ThemeProvider attribute="class" defaultTheme="light" enableSystem storageKey="bmw-product-theme" disableTransitionOnChange>{children}</ThemeProvider>
}

export function AppearanceToggle() {
  const { resolvedTheme, setTheme } = useTheme()
  return <Button variant="ghost" size="icon" aria-label="Toggle color theme" onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}>
    <Moon className="size-4 dark:hidden" /><Sun className="hidden size-4 dark:block" />
  </Button>
}
