import "server-only"
import { db } from "@/lib/db"
import type { AccountSource } from "@/lib/account-sources"

export type LatestImport = {
  source: AccountSource
  imported_at: string | null
  date_from: string | null
  date_to: string | null
}

export async function getLatestImports(): Promise<LatestImport[]> {
  const rows = await db`
    with sources(account_id, source) as (
      values ('revolut_eur'::text, 'Revolut'::text), ('sparkasse_giro'::text, 'Sparkasse'::text)
    )
    select
      sources.source,
      to_char(latest.imported_at at time zone 'Europe/Madrid', 'YYYY-MM-DD HH24:MI') as imported_at,
      to_char(latest.date_from, 'YYYY-MM-DD') as date_from,
      to_char(latest.date_to, 'YYYY-MM-DD') as date_to
    from sources
    left join lateral (
      select imported_at, date_from, date_to
      from imports
      where account_id = sources.account_id
      order by imported_at desc, id desc
      limit 1
    ) as latest on true
    order by sources.source
  `
  return rows as unknown as LatestImport[]
}
