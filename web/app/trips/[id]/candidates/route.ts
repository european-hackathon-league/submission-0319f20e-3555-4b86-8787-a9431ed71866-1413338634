import { NextRequest, NextResponse } from "next/server"
import { z } from "zod"
import { getCandidateTransactions } from "@/lib/queries/trips"

const querySchema = z.object({
  from: z.iso.date(),
  to: z.iso.date(),
  q: z.string().max(200).default(""),
}).refine((query) => query.from <= query.to)

export async function GET(request: NextRequest, { params }: RouteContext<"/trips/[id]/candidates">) {
  const { id } = await params
  if (!/^[1-9]\d{0,18}$/.test(id)) return NextResponse.json({ error: "Invalid trip" }, { status: 400 })
  const parsed = querySchema.safeParse({
    from: request.nextUrl.searchParams.get("from"),
    to: request.nextUrl.searchParams.get("to"),
    q: request.nextUrl.searchParams.get("q") ?? "",
  })
  if (!parsed.success) return NextResponse.json({ error: "Invalid search" }, { status: 400 })
  const { from, to, q } = parsed.data
  const rows = await getCandidateTransactions(id, from, to, q.trim())
  return NextResponse.json(rows)
}
