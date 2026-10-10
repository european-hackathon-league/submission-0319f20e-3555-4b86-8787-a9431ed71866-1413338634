import { monthStart, shiftDate, today, type Range } from "@/lib/filters"

export type TrendCategoryRow = { month: string; category: string; parent_category: string | null; spend: number }
export type TrendMonth = { month: string; spend: number; partial: boolean }
export type TrendCategory = { category: string; spend: number; share: number; children: { category: string; spend: number }[] }
export type CategoryChange = { category: string; current: number; previous: number; change: number; children: { category: string; current: number; previous: number }[] }

export function buildTrendInsights(
  monthlyRows: { month: string; spend: number }[],
  categoryRows: TrendCategoryRow[],
  range: Range,
  currentDate = today(),
) {
  const firstMonth = range.from?.slice(0, 7) ?? monthlyRows[0]?.month
  const lastDate = range.to && range.to < currentDate ? range.to : currentDate
  const lastMonth = range.to ? lastDate.slice(0, 7) : monthlyRows.at(-1)?.month
  const byMonth = new Map(monthlyRows.map((row) => [row.month, row.spend]))
  const months: TrendMonth[] = []

  if (firstMonth && lastMonth && firstMonth <= lastMonth) {
    for (let month = firstMonth; month <= lastMonth; month = monthStart(`${month}-01`, 1).slice(0, 7)) {
      const start = `${month}-01`
      const end = shiftDate(monthStart(start, 1), -1)
      months.push({
        month,
        spend: byMonth.get(month) ?? 0,
        partial: Boolean((range.from && range.from > start) || lastDate < end),
      })
    }
  }

  const total = months.reduce((sum, row) => sum + row.spend, 0)
  const completeMonths = months.filter((row) => !row.partial)
  const average = completeMonths.length
    ? completeMonths.reduce((sum, row) => sum + row.spend, 0) / completeMonths.length
    : null
  const latest = completeMonths.at(-1) ?? null
  const previous = completeMonths.at(-2) ?? null

  const categoryTotals = new Map<string, number>()
  const categoryMonths = new Map<string, Map<string, number>>()
  const childTotals = new Map<string, Map<string, number>>()
  const childMonths = new Map<string, Map<string, Map<string, number>>>()
  for (const row of categoryRows) {
    const root = row.parent_category ?? row.category
    categoryTotals.set(root, (categoryTotals.get(root) ?? 0) + row.spend)
    const month = categoryMonths.get(row.month) ?? new Map<string, number>()
    month.set(root, (month.get(root) ?? 0) + row.spend)
    categoryMonths.set(row.month, month)
    if (row.parent_category) {
      const children = childTotals.get(root) ?? new Map<string, number>()
      children.set(row.category, (children.get(row.category) ?? 0) + row.spend)
      childTotals.set(root, children)
      const monthChildren = childMonths.get(row.month) ?? new Map<string, Map<string, number>>()
      const rootChildren = monthChildren.get(root) ?? new Map<string, number>()
      rootChildren.set(row.category, (rootChildren.get(row.category) ?? 0) + row.spend)
      monthChildren.set(root, rootChildren)
      childMonths.set(row.month, monthChildren)
    }
  }

  const ranked = [...categoryTotals]
    .filter(([, spend]) => spend > 0)
    .sort((a, b) => b[1] - a[1])
  const positiveCategoryTotal = ranked.reduce((sum, [, spend]) => sum + spend, 0)
  const categoryList = ranked.map(([category, spend]) => ({
    category, spend, share: positiveCategoryTotal > 0 ? spend / positiveCategoryTotal : 0,
    children: [...(childTotals.get(category) ?? new Map())].map(([name, value]) => ({ category: name, spend: value })).sort((a, b) => b.spend - a.spend),
  }))

  const currentCategories = latest ? categoryMonths.get(latest.month) : undefined
  const previousCategories = previous ? categoryMonths.get(previous.month) : undefined
  const lastSelected = months.at(-1)
  const lastSelectedCategories = lastSelected ? categoryMonths.get(lastSelected.month) : undefined
  const leadingLastCategory = lastSelectedCategories
    ? [...lastSelectedCategories].sort((a, b) => b[1] - a[1])[0]
    : undefined
  const partialInsight = lastSelected?.partial && lastSelected.spend > 0 && leadingLastCategory && leadingLastCategory[1] > 0
    ? { month: lastSelected.month, spend: lastSelected.spend, category: leadingLastCategory[0], categorySpend: leadingLastCategory[1] }
    : null
  const names = new Set([...(currentCategories?.keys() ?? []), ...(previousCategories?.keys() ?? [])])
  const changes: CategoryChange[] = latest && previous
    ? [...names].map((category) => {
        const current = currentCategories?.get(category) ?? 0
        const previousSpend = previousCategories?.get(category) ?? 0
        const currentChildren = childMonths.get(latest.month)?.get(category)
        const previousChildren = childMonths.get(previous.month)?.get(category)
        const childNames = new Set([...(currentChildren?.keys() ?? []), ...(previousChildren?.keys() ?? [])])
        const children = [...childNames].map((name) => ({ category: name, current: currentChildren?.get(name) ?? 0, previous: previousChildren?.get(name) ?? 0 }))
          .sort((a, b) => Math.abs(b.current - b.previous) - Math.abs(a.current - a.previous))
        return { category, current, previous: previousSpend, change: current - previousSpend, children }
      }).filter((row) => Math.abs(row.change) >= 0.01)
        .sort((a, b) => Math.abs(b.change) - Math.abs(a.change)).slice(0, 5)
    : []

  return { months, total, completeCount: completeMonths.length, average, latest, previous, categories: categoryList satisfies TrendCategory[], changes, partialInsight }
}
