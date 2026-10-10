import { Clock3 } from "lucide-react"
import { connection } from "next/server"
import { ACCOUNT_SOURCE_DOT_COLORS } from "@/lib/account-sources"
import { getLatestImports } from "@/lib/queries/imports"

const uploadDateFormatter = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
})

function uploadDate(value: string | null) {
  return value ? uploadDateFormatter.format(new Date(`${value.slice(0, 10)}T12:00:00Z`)) : "Never"
}

export async function LastSynced() {
  // Read live import status only when a request arrives, not during the build.
  await connection()
  const imports = await getLatestImports()
  const syncSummary = imports.map((item) => `${item.source}: ${uploadDate(item.imported_at)}`).join(". ")

  return (
    <section aria-labelledby="last-synced-title" className="px-2 pb-2 group-data-[collapsible=icon]:px-0">
      <div
        role="img"
        title={syncSummary}
        aria-label={`Last synced. ${syncSummary}`}
        className="hidden h-8 items-center justify-center text-sidebar-foreground/70 group-data-[collapsible=icon]:flex"
      >
        <Clock3 className="size-4" aria-hidden="true" />
      </div>
      <h2 id="last-synced-title" className="px-2 pb-2 text-xs font-semibold text-sidebar-foreground/70 group-data-[collapsible=icon]:hidden">
        Last synced
      </h2>
      <div className="space-y-1 group-data-[collapsible=icon]:hidden">
        {imports.map((item) => (
          <div key={item.source} className="flex items-center gap-2 px-2 py-0.5 text-xs">
            <span
              aria-hidden="true"
              className={`size-2 shrink-0 rounded-none ${ACCOUNT_SOURCE_DOT_COLORS[item.source]}`}
            />
            <span className="min-w-0 flex-1 font-medium">{item.source}</span>
            <time dateTime={item.imported_at?.slice(0, 10)} className="shrink-0 tabular-nums text-muted-foreground">
              {uploadDate(item.imported_at)}
            </time>
          </div>
        ))}
      </div>
    </section>
  )
}
