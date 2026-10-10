"use client"

import { useState, useTransition, type FormEvent } from "react"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { ArrowDown, ArrowUp, ChevronDown, Columns3, MoreHorizontal, Search, X } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { CategoryPicker } from "@/components/category-picker"
import { Button } from "@/components/ui/button"
import { DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuGroup, DropdownMenuItem, DropdownMenuLabel, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { excludeTransaction, resetTransaction } from "@/app/trips/actions"
import { Input } from "@/components/ui/input"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { ALL_TIME_URL, formatDate, money } from "@/lib/filters"
import type { Transaction } from "@/lib/queries/types"
import type { TransactionOptions } from "@/lib/queries/transactions"
import type { CategoryOption } from "@/lib/queries/categories"
import type { TripTransaction } from "@/lib/queries/trips"

const typeLabels = ["expense", "income", "transfer", "cash", "fee", "refund"]
const columnLabels = ["Date", "Merchant", "Category", "Account", "Type", "Amount"] as const
type Column = typeof columnLabels[number]
const columnWidths: Record<Column | "Trip" | "Actions", number> = {
  Date: 13, Merchant: 23, Category: 22, Account: 17, Type: 12, Amount: 13,
  Trip: 14, Actions: 4,
}
const monthFormatter = new Intl.DateTimeFormat("en-US", { month: "long", year: "numeric", timeZone: "UTC" })
const monthNameFormatter = new Intl.DateTimeFormat("en-GB", { month: "long", timeZone: "UTC" })
const fullDateFormatter = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" })

function groupForDate(date: string, groupBy: TransactionOptions["groupBy"]) {
  if (groupBy === "none") return null
  if (groupBy === "day") {
    return { key: date, label: fullDateFormatter.format(new Date(`${date}T12:00:00Z`)) }
  }
  if (groupBy === "month") {
    const key = date.slice(0, 7)
    return { key, label: monthFormatter.format(new Date(`${key}-01T12:00:00Z`)) }
  }
  const monday = new Date(`${date}T12:00:00Z`)
  monday.setUTCDate(monday.getUTCDate() - ((monday.getUTCDay() + 6) % 7))
  const key = monday.toISOString().slice(0, 10)
  const sunday = new Date(monday)
  sunday.setUTCDate(sunday.getUTCDate() + 6)
  const label = monday.getUTCFullYear() !== sunday.getUTCFullYear()
    ? `${fullDateFormatter.format(monday)} – ${fullDateFormatter.format(sunday)}`
    : monday.getUTCMonth() !== sunday.getUTCMonth()
      ? `${monday.getUTCDate()} ${monthNameFormatter.format(monday)} – ${fullDateFormatter.format(sunday)}`
      : `${monday.getUTCDate()}–${fullDateFormatter.format(sunday)}`
  return { key, label }
}

function TransactionDetails({ row, categories, onCategoryChange }: {
  row: Transaction
  categories: CategoryOption[]
  onCategoryChange: (value: { category: string | null; parent: string | null }) => void
}) {
  const details: [string, string][] = [
    ["Description", row.description_raw ?? "—"], ["Counterparty", row.counterparty_raw ?? "—"],
    ["Fee", money.format(row.fee)],
    ["Original amount", row.original_amount == null ? "—" : `${new Intl.NumberFormat("de-DE", { maximumFractionDigits: 2 }).format(row.original_amount)} ${row.original_currency ?? ""}`],
    ["FX rate", row.fx_rate == null ? "—" : new Intl.NumberFormat("de-DE", { maximumFractionDigits: 8 }).format(row.fx_rate)],
    ["Booking date", formatDate(row.booking_date)], ["Value date", formatDate(row.value_date)],
    ["Status", row.status], ["Account", row.account_name],
  ]
  return <><SheetHeader><SheetTitle>{row.merchant || row.counterparty_raw || "Transaction"}</SheetTitle><SheetDescription>{formatDate(row.date)} · {row.type}</SheetDescription></SheetHeader>
    <div className="overflow-y-auto px-4 pb-6"><div className={`mb-5 text-3xl font-semibold tabular-nums ${row.amount < 0 ? "text-destructive" : "text-success"}`}>{money.format(row.amount)}</div>
      <dl className="divide-y">{details.map(([label, value]) => <div key={label} className="grid grid-cols-2 gap-3 py-3 text-sm"><dt className="text-muted-foreground">{label}</dt><dd className="break-words text-right">{value}</dd></div>)}
        <div className="grid grid-cols-2 items-center gap-3 py-3 text-sm"><dt className="text-muted-foreground">Category</dt><dd className="min-w-0 text-right"><CategoryPicker transactionId={row.id} category={row.category} parent={row.parent_category} categories={categories} inDetails onCategoryChange={onCategoryChange} /></dd></div>
      </dl>
    </div></>
}

export function DataTable({ rows, total, categories, options, tripId }: {
  rows: Transaction[]; total: number; categories: CategoryOption[]; options: TransactionOptions; tripId?: string
}) {
  const pathname = usePathname()
  const router = useRouter()
  const searchParams = useSearchParams()
  const [searchText, setSearchText] = useState(options.search)
  const [selected, setSelected] = useState<Transaction | null>(null)
  const [visible, setVisible] = useState<Column[]>([...columnLabels])
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(() => new Set())
  const [pending, startTransition] = useTransition()
  function navigate(patch: Record<string, string | null>) {
    const params = new URLSearchParams(searchParams.toString())
    for (const [key, value] of Object.entries(patch)) {
      if (value) params.set(key, value)
      else params.delete(key)
    }
    router.push(`${pathname}?${params.toString()}`, { scroll: false })
  }
  function toggleList(key: "type" | "category", item: string) {
    const current = new Set((searchParams.get(key) ?? "").split(",").filter(Boolean))
    if (current.has(item)) current.delete(item); else current.add(item)
    navigate({ [key]: [...current].join(",") || null, page: null })
  }
  function toggleCategory(name: string, root?: CategoryOption) {
    const current = new Set(options.categories)
    if (current.has(name)) current.delete(name)
    else {
      current.add(name)
      if (root) root.children.forEach((child) => current.delete(child))
      else {
        const parent = categories.find((group) => group.children.includes(name))
        if (parent) current.delete(parent.name)
      }
    }
    navigate({ category: [...current].join(",") || null, page: null })
  }
  function sort(column: "date" | "amount") {
    navigate({ sort: column, dir: options.sort === column && options.direction === "desc" ? "asc" : "desc", page: null })
  }
  function submitSearch(event: FormEvent) {
    event.preventDefault()
    navigate({ q: searchText.trim() || null, page: null })
  }
  function clearFilters() {
    setSearchText("")
    navigate({
      account: null,
      category: null,
      from: pathname === "/monthly" ? null : ALL_TIME_URL.from,
      page: null,
      q: null,
      range: pathname === "/monthly" ? null : "all",
      to: pathname === "/monthly" ? null : ALL_TIME_URL.to,
      type: null,
    })
  }
  const usesGlobalDateRange = pathname !== "/monthly" && !pathname.startsWith("/trips/")
  const allTime = searchParams.get("range") === "all" || (searchParams.get("from") === ALL_TIME_URL.from && searchParams.get("to") === ALL_TIME_URL.to)
  const hasActiveFilters = Boolean(
    options.search || options.types.length || options.categories.length || searchParams.has("account") || (usesGlobalDateRange && !allTime),
  )
  const columns = visible.map((column) => ({ column, align: column === "Amount" ? "text-right" : "" }))
  const tableColumns: (Column | "Trip" | "Actions")[] = [...visible, ...(tripId ? ["Trip", "Actions"] as const : [])]
  const totalColumnWidth = tableColumns.reduce((total, column) => total + columnWidths[column], 0)
  const normalizedColumnWidths = tableColumns.map((column) => columnWidths[column] / totalColumnWidth * 100)
  const columnCount = Math.max(1, visible.length + (tripId ? 2 : 0))
  const groupedRows: { key: string; label: string; rows: Transaction[] }[] = []
  if (options.groupBy !== "none") {
    for (const row of rows) {
      const group = groupForDate(row.date, options.groupBy)
      if (!group) continue
      const last = groupedRows.at(-1)
      if (last?.key === group.key) last.rows.push(row)
      else groupedRows.push({ ...group, rows: [row] })
    }
  }
  function renderTable(tableRows: Transaction[]) {
    return <div className="overflow-x-auto rounded-lg border"><Table className={`table-fixed ${tripId ? "min-w-[64rem]" : "min-w-[52rem]"}`}><colgroup>{normalizedColumnWidths.map((width, index) => <col key={tableColumns[index]} style={{ width: `${width}%` }} />)}</colgroup><TableHeader><TableRow>{columns.map(({ column, align }) => <TableHead key={column} className={align}>{column === "Date" || column === "Amount" ? <Button variant="ghost" size="sm" className={column === "Amount" ? "ml-auto" : "-ml-2"} onClick={() => sort(column.toLowerCase() as "date" | "amount")}>{column}{options.sort === column.toLowerCase() ? options.direction === "desc" ? <ArrowDown /> : <ArrowUp /> : null}</Button> : column}</TableHead>)}{tripId && <><TableHead>Trip</TableHead><TableHead className="w-10"><span className="sr-only">Actions</span></TableHead></>}</TableRow></TableHeader>
      <TableBody>{tableRows.length === 0 ? <TableRow><TableCell colSpan={columnCount} className="h-40 text-center text-muted-foreground">No transactions match these filters.</TableCell></TableRow> : tableRows.map((row) => <TableRow key={row.id} className={row.amount > 0 ? "cursor-pointer bg-success/5 hover:bg-success/10" : "cursor-pointer"} tabIndex={0} onClick={() => setSelected(row)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setSelected(row) } }} aria-label={`View transaction from ${row.merchant || row.counterparty_raw || "Unknown"}`}>
        {visible.includes("Date") && <TableCell>{formatDate(row.date)}</TableCell>}
        {visible.includes("Merchant") && <TableCell className="max-w-64 truncate font-medium">{row.merchant || row.counterparty_raw || "Unknown"}</TableCell>}
        {visible.includes("Category") && <TableCell onClick={(event) => event.stopPropagation()} onKeyDown={(event) => event.stopPropagation()}><CategoryPicker transactionId={row.id} category={row.category} parent={row.parent_category} categories={categories} /></TableCell>}
        {visible.includes("Account") && <TableCell>{row.account_name}</TableCell>}
        {visible.includes("Type") && <TableCell><Badge variant="outline" className="capitalize">{row.type}</Badge></TableCell>}
        {visible.includes("Amount") && <TableCell className={`text-right font-medium tabular-nums ${row.amount < 0 ? "text-destructive" : "text-success"}`}>{money.format(row.amount)}</TableCell>}
        {tripId && <><TableCell>{(row as TripTransaction).manually_added ? <Badge variant="secondary">Manually added</Badge> : "—"}</TableCell><TableCell onClick={(event) => event.stopPropagation()} onKeyDown={(event) => event.stopPropagation()}><DropdownMenu><DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" aria-label="Trip transaction actions" disabled={pending} />}><MoreHorizontal /></DropdownMenuTrigger><DropdownMenuContent align="end"><DropdownMenuItem onClick={() => startTransition(async () => { if ((row as TripTransaction).overridden) await resetTransaction(tripId, row.id); else await excludeTransaction(tripId, row.id) })}>{(row as TripTransaction).overridden ? "Reset override" : "Remove from trip"}</DropdownMenuItem></DropdownMenuContent></DropdownMenu></TableCell></>}
      </TableRow>)}</TableBody></Table></div>
  }
  const pageCount = Math.max(1, Math.ceil(total / 50))
  return <div className="space-y-4">
    <div className="flex flex-wrap items-center gap-2">
      <form onSubmit={submitSearch} className="flex min-w-48 flex-1 items-center gap-2 sm:max-w-sm"><Input value={searchText} onChange={(event) => setSearchText(event.target.value)} placeholder="Search merchant or description" aria-label="Search transactions" /><Button type="submit" variant="outline" size="icon" aria-label="Search"><Search /></Button></form>
      <DropdownMenu><DropdownMenuTrigger render={<Button variant="outline" />}>Type{options.types.length ? ` (${options.types.length})` : ""}</DropdownMenuTrigger><DropdownMenuContent><DropdownMenuGroup><DropdownMenuLabel>Transaction type</DropdownMenuLabel>{typeLabels.map((type) => <DropdownMenuCheckboxItem key={type} checked={options.types.includes(type)} onCheckedChange={() => toggleList("type", type)}>{type}</DropdownMenuCheckboxItem>)}</DropdownMenuGroup></DropdownMenuContent></DropdownMenu>
      <DropdownMenu><DropdownMenuTrigger render={<Button variant="outline" />}>Category{options.categories.length ? ` (${options.categories.length})` : ""}</DropdownMenuTrigger><DropdownMenuContent className="max-h-80 min-w-64 overflow-y-auto"><DropdownMenuGroup><DropdownMenuLabel>Categories</DropdownMenuLabel><DropdownMenuCheckboxItem checked={options.categories.includes("Uncategorized")} onCheckedChange={() => toggleCategory("Uncategorized")}>Uncategorized</DropdownMenuCheckboxItem><div className="my-1 border-b" />{categories.map((group) => <div key={group.name}>
        <div className="flex items-center"><DropdownMenuCheckboxItem className="min-w-0 flex-1" checked={options.categories.includes(group.name)} onCheckedChange={() => toggleCategory(group.name, group)}>{group.name}</DropdownMenuCheckboxItem><button type="button" className="mr-1 rounded p-1.5 hover:bg-accent focus-visible:outline-2 focus-visible:outline-primary" aria-label={`${expandedCategories.has(group.name) ? "Hide" : "Show"} ${group.name} subcategories`} aria-expanded={expandedCategories.has(group.name)} onClick={() => setExpandedCategories((current) => { const next = new Set(current); if (next.has(group.name)) next.delete(group.name); else next.add(group.name); return next })}><ChevronDown className={`size-4 transition-transform ${expandedCategories.has(group.name) ? "" : "-rotate-90"}`} /></button></div>
        {expandedCategories.has(group.name) && <div className="border-l pl-3 ml-3">{group.children.map((child) => <DropdownMenuCheckboxItem key={child} checked={options.categories.includes(child)} onCheckedChange={() => toggleCategory(child)}>{child}</DropdownMenuCheckboxItem>)}</div>}
      </div>)}</DropdownMenuGroup></DropdownMenuContent></DropdownMenu>
      <DropdownMenu><DropdownMenuTrigger render={<Button variant="outline" />}>Group: {options.groupBy === "none" ? "None" : options.groupBy === "day" ? "Day" : options.groupBy === "week" ? "Week" : "Month"}</DropdownMenuTrigger><DropdownMenuContent><DropdownMenuRadioGroup value={options.groupBy} onValueChange={(value) => navigate({ group: value === "none" ? null : value, page: null })}><DropdownMenuLabel>Group transactions</DropdownMenuLabel><DropdownMenuRadioItem value="none">None</DropdownMenuRadioItem><DropdownMenuRadioItem value="day">Day</DropdownMenuRadioItem><DropdownMenuRadioItem value="week">Week</DropdownMenuRadioItem><DropdownMenuRadioItem value="month">Month</DropdownMenuRadioItem></DropdownMenuRadioGroup></DropdownMenuContent></DropdownMenu>
      <DropdownMenu><DropdownMenuTrigger render={<Button variant="outline" aria-label="Visible columns" />}><Columns3 /> Columns</DropdownMenuTrigger><DropdownMenuContent><DropdownMenuGroup><DropdownMenuLabel>Visible columns</DropdownMenuLabel>{columnLabels.map((column) => <DropdownMenuCheckboxItem key={column} checked={visible.includes(column)} onCheckedChange={() => setVisible((current) => current.includes(column) ? current.filter((item) => item !== column) : [...current, column])}>{column}</DropdownMenuCheckboxItem>)}</DropdownMenuGroup></DropdownMenuContent></DropdownMenu>
      {hasActiveFilters && <Button type="button" variant="ghost" size="sm" onClick={clearFilters}><X />Clear filters</Button>}
    </div>
    {groupedRows.length ? <div className="space-y-6">{groupedRows.map((group) => <section key={group.key} aria-label={`${options.groupBy === "day" ? "Day" : options.groupBy === "week" ? "Week" : "Month"}: ${group.label}`}>
      <div className="mb-3 px-1"><p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{options.groupBy === "day" ? "Day" : options.groupBy === "week" ? "Week" : "Month"}</p><h3 className="text-base font-semibold tracking-tight">{group.label}</h3></div>
      {renderTable(group.rows)}
    </section>)}</div> : renderTable(rows)}
    <div className="flex items-center justify-between gap-3 text-sm text-muted-foreground"><span>{total.toLocaleString("de-DE")} transactions · page {options.page} of {pageCount}</span><div className="flex gap-2"><Button variant="outline" size="sm" disabled={options.page <= 1} onClick={() => navigate({ page: String(options.page - 1) })}>Previous</Button><Button variant="outline" size="sm" disabled={options.page >= pageCount} onClick={() => navigate({ page: String(options.page + 1) })}>Next</Button></div></div>
    <Sheet open={selected !== null} onOpenChange={(open) => { if (!open) setSelected(null) }}><SheetContent>{selected && <TransactionDetails row={selected} categories={categories} onCategoryChange={(value) => setSelected((current) => current?.id === selected.id ? { ...current, category: value.category, parent_category: value.parent } : current)} />}</SheetContent></Sheet>
  </div>
}
