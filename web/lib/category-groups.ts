export type CategoryAmount = { category: string; spend: number }
export type CategoryGroup = CategoryAmount & { children: CategoryAmount[] }

export function groupCategorySpend(rows: { category: string; parent_category: string | null; spend: number }[]): CategoryGroup[] {
  const groups = new Map<string, CategoryGroup>()
  for (const row of rows) {
    const root = row.parent_category ?? row.category
    const group = groups.get(root) ?? { category: root, spend: 0, children: [] }
    group.spend += Number(row.spend)
    if (row.parent_category) group.children.push({ category: row.category, spend: Number(row.spend) })
    groups.set(root, group)
  }
  return [...groups.values()]
    .map((group) => ({ ...group, children: group.children.sort((a, b) => b.spend - a.spend) }))
    .sort((a, b) => b.spend - a.spend)
}
