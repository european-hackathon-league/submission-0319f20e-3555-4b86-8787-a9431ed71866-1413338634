import Link from "next/link"
import { Eye, EyeOff } from "lucide-react"
import { buttonVariants } from "@/components/ui/button"

export function HousingUtilitiesToggle({ href, excluded }: { href: string; excluded: boolean }) {
  return <Link href={href} className={buttonVariants({ variant: excluded ? "secondary" : "outline", size: "sm" })}>
    {excluded ? <Eye /> : <EyeOff />}
    {excluded ? "Show housing & utilities" : "Hide housing & utilities"}
  </Link>
}
