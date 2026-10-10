import "server-only"
import { db } from "@/lib/db"

export type CategoryOption = { name: string; children: string[] }

export async function getCategoryOptions(kind?: "spend"): Promise<CategoryOption[]> {
  const rows = await db`select p.name, c.name as child
    from categories p left join categories c on c.parent_id = p.id
    where p.parent_id is null and (${kind ?? null}::text is null or p.kind in (${kind ?? null}, 'other'))
    order by p.name, c.name`
  const options = new Map<string, CategoryOption>()
  for (const row of rows) {
    const name = String(row.name)
    const group = options.get(name) ?? { name, children: [] }
    if (row.child) group.children.push(String(row.child))
    options.set(name, group)
  }
  return [...options.values()]
}
