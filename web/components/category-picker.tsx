"use client"

import { useOptimistic, useState, useTransition } from "react"
import { ArrowLeft, ChevronDown, ChevronRight, Search } from "lucide-react"
import { updateTransactionCategory } from "@/app/transactions/actions"
import { CategoryBadge } from "@/components/category-badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import type { CategoryOption } from "@/lib/queries/categories"

type CategoryValue = { category: string | null; parent: string | null }

export function CategoryPicker({
  transactionId,
  category,
  parent,
  categories,
  inDetails = false,
  onCategoryChange,
}: {
  transactionId: string
  category: string | null
  parent: string | null
  categories: CategoryOption[]
  inDetails?: boolean
  onCategoryChange?: (value: CategoryValue) => void
}) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState("")
  const [activeParent, setActiveParent] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pending, startTransition] = useTransition()
  const [value, setOptimisticValue] = useOptimistic<CategoryValue, CategoryValue>(
    { category, parent },
    (_current, next) => next,
  )
  const normalizedSearch = search.trim().toLocaleLowerCase()
  const selectedParent = categories.find((group) => group.name === activeParent) ?? null
  const filteredParents = categories.filter((group) =>
    group.children.length > 0 && (!normalizedSearch || group.name.toLocaleLowerCase().includes(normalizedSearch)
      || group.children.some((child) => child.toLocaleLowerCase().includes(normalizedSearch))),
  )
  const filteredChildren = selectedParent?.children.filter((child) =>
    !normalizedSearch || child.toLocaleLowerCase().includes(normalizedSearch),
  ) ?? []

  function choose(next: CategoryValue) {
    setOpen(false)
    setSearch("")
    setActiveParent(null)
    setError(null)
    startTransition(async () => {
      setOptimisticValue(next)
      try {
        await updateTransactionCategory(transactionId, next.category)
        onCategoryChange?.(next)
      } catch {
        setError("Could not save the category. Please try again.")
        setOpen(true)
      }
    })
  }

  const currentName = value.category ?? "Uncategorized"
  const buttonLabel = value.parent ? `${value.parent} / ${currentName}` : currentName

  return <Popover open={open} onOpenChange={(nextOpen) => {
    setOpen(nextOpen)
    setSearch("")
    if (nextOpen) {
      setActiveParent(null)
      setError(null)
    }
  }}>
    <PopoverTrigger render={<Button
      type="button"
      variant="ghost"
      size="sm"
      disabled={pending}
      aria-label={`Change category for this transaction. Current category: ${buttonLabel}`}
      className={inDetails ? "h-9 w-full min-w-0 justify-between gap-1.5 px-1" : "h-auto w-full min-w-0 justify-between gap-1 px-1 py-1"}
    />}>
      <CategoryBadge category={value.category} parent={value.parent} className="min-w-0 max-w-[calc(100%-1rem)]" />
      <ChevronDown aria-hidden="true" className="size-3.5 shrink-0 text-muted-foreground" />
    </PopoverTrigger>
    <PopoverContent align="start" side="bottom" className="w-80 gap-2 p-2">
      <div className="flex min-h-9 items-center gap-2 px-1">
        {selectedParent ? <>
          <Button type="button" variant="ghost" size="icon-sm" aria-label="Back to categories" onClick={() => { setActiveParent(null); setSearch("") }}><ArrowLeft /></Button>
          <div className="min-w-0"><p className="truncate text-sm font-medium">{selectedParent.name}</p><p className="text-xs text-muted-foreground">Choose a subcategory</p></div>
        </> : <div><p className="text-sm font-medium">Choose a category</p><p className="text-xs text-muted-foreground">Then choose a subcategory</p></div>}
      </div>
      <label className="relative block">
        <Search aria-hidden="true" className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input autoFocus value={search} onChange={(event) => setSearch(event.target.value)} placeholder={selectedParent ? "Find a subcategory…" : "Find a category…"} aria-label={selectedParent ? "Find a subcategory" : "Find a category"} className="pl-8" />
      </label>
      <div className="max-h-72 overflow-y-auto overscroll-contain" role="group" aria-label="Transaction categories">
        {error && <p role="alert" className="px-2.5 py-2 text-sm text-destructive">{error}</p>}
        {!selectedParent && (!normalizedSearch || "uncategorized".includes(normalizedSearch)) && <button type="button" disabled={pending} aria-pressed={value.category === null} onClick={() => choose({ category: null, parent: null })} className={value.category === null ? "mb-1 flex w-full items-center justify-between rounded-md bg-accent px-2.5 py-2 text-left text-sm font-medium text-accent-foreground focus-visible:outline-none" : "mb-1 flex w-full items-center justify-between rounded-md px-2.5 py-2 text-left text-sm hover:bg-accent hover:text-accent-foreground focus-visible:bg-accent focus-visible:outline-none"}>
          <span>Uncategorized</span>{value.category === null && <span className="text-xs text-muted-foreground">Current</span>}
        </button>}
        {!selectedParent && <div className="mb-1 border-b" />}
        {selectedParent ? filteredChildren.length ? filteredChildren.map((child) => {
            const selected = value.category === child
            return <button type="button" key={child} disabled={pending} aria-pressed={selected} onClick={() => choose({ category: child, parent: selectedParent.name })} className={`flex w-full items-center justify-between gap-3 rounded-md px-2.5 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground focus-visible:bg-accent focus-visible:outline-none ${selected ? "bg-accent font-medium text-accent-foreground" : ""}`}>
              <span className="truncate">{child}</span>
              {selected && <span className="text-xs text-muted-foreground">Current</span>}
            </button>
          }) : <p className="px-2.5 py-6 text-center text-sm text-muted-foreground">No matching subcategories.</p>
          : filteredParents.length ? filteredParents.map((group) => <button type="button" key={group.name} onClick={() => {
            const matchingSubcategory = normalizedSearch && group.children.some((child) => child.toLocaleLowerCase().includes(normalizedSearch))
            setActiveParent(group.name)
            setSearch(matchingSubcategory ? search : "")
          }} className="flex w-full items-center justify-between gap-3 rounded-md px-2.5 py-2 text-left text-sm hover:bg-accent hover:text-accent-foreground focus-visible:bg-accent focus-visible:outline-none">
            <span className="truncate font-medium">{group.name}</span><span className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground">{group.children.length} subcategories<ChevronRight aria-hidden="true" className="size-4" /></span>
          </button>) : <p className="px-2.5 py-6 text-center text-sm text-muted-foreground">No matching categories.</p>}
      </div>
      {pending && <p role="status" className="px-1 text-xs text-muted-foreground">Saving category…</p>}
    </PopoverContent>
  </Popover>
}
