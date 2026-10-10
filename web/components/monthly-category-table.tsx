"use client"

import { useState } from "react"
import { ChevronDown } from "lucide-react"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { money } from "@/lib/filters"

type Row = { category: string; spend: number; previous: number }
type Group = Row & { children: Row[] }

function amounts(row: Row) {
  const delta = row.spend - row.previous
  const pct = row.previous === 0 ? null : delta / Math.abs(row.previous) * 100
  const color = delta > 0 ? "text-destructive" : delta < 0 ? "text-green-700 dark:text-green-400" : ""
  return <>
    <TableCell className="text-right tabular-nums">{money.format(row.spend)}</TableCell>
    <TableCell className="text-right tabular-nums">{money.format(row.previous)}</TableCell>
    <TableCell className="text-right font-bold tabular-nums text-foreground">{money.format(delta)}</TableCell>
    <TableCell className={`text-right tabular-nums ${color}`}>{pct == null ? "—" : `${pct > 0 ? "+" : ""}${pct.toFixed(1)}%`}</TableCell>
  </>
}

export function MonthlyCategoryTable({ groups }: { groups: Group[] }) {
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set())
  function toggle(name: string) {
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(name)) next.delete(name); else next.add(name)
      return next
    })
  }
  return <Table><TableHeader><TableRow><TableHead>Category</TableHead><TableHead className="text-right">This month</TableHead><TableHead className="text-right">Previous month</TableHead><TableHead className="text-right">Delta</TableHead><TableHead className="text-right">Delta %</TableHead></TableRow></TableHeader>
    <TableBody>{groups.map((group) => <FragmentGroup key={group.category} group={group} open={expanded.has(group.category)} onToggle={() => toggle(group.category)} />)}</TableBody>
  </Table>
}

function FragmentGroup({ group, open, onToggle }: { group: Group; open: boolean; onToggle: () => void }) {
  return <>
    <TableRow><TableCell><button type="button" className="flex w-full items-center gap-2 text-left font-medium hover:text-primary focus-visible:outline-2 focus-visible:outline-primary" aria-expanded={open} aria-label={`${open ? "Hide" : "Show"} ${group.category} subcategories`} onClick={onToggle}><ChevronDown className={`size-4 shrink-0 transition-transform ${open ? "" : "-rotate-90"}`} />{group.category}</button></TableCell>{amounts(group)}</TableRow>
    {open && group.children.map((child) => <TableRow key={child.category} className="bg-muted/30"><TableCell className="pl-10 text-muted-foreground">{child.category}</TableCell>{amounts(child)}</TableRow>)}
  </>
}
