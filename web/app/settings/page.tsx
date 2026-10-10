import { ChevronDown } from "lucide-react"
import { PageHeading } from "@/components/dashboard-shell"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { getCategoryOptions } from "@/lib/queries/categories"

export const dynamic = "force-dynamic"

export default async function SettingsPage() {
  const categories = await getCategoryOptions()
  return <main className="space-y-4">
    <PageHeading title="Settings" description="Your finance categories and account preferences." />
    <Card><CardHeader><CardTitle>Categories</CardTitle><CardDescription>Transactions and merchant rules use the subcategories shown under each broad category.</CardDescription></CardHeader>
      <CardContent className="divide-y">{categories.map((group) => <details key={group.name} className="group py-1">
        <summary className="flex cursor-pointer list-none items-center gap-3 rounded-md px-2 py-3 focus-visible:outline-2 focus-visible:outline-primary [&::-webkit-details-marker]:hidden"><span className="min-w-0 flex-1 font-medium">{group.name}</span><span className="text-xs text-muted-foreground">{group.children.length} subcategories</span><ChevronDown className="size-4 shrink-0 -rotate-90 text-muted-foreground transition-transform group-open:rotate-0" /></summary>
        <div className="mb-2 ml-4 border-l pl-4">{group.children.map((child) => <div key={child} className="py-2 text-sm text-muted-foreground">{child}</div>)}</div>
      </details>)}</CardContent>
    </Card>
  </main>
}
