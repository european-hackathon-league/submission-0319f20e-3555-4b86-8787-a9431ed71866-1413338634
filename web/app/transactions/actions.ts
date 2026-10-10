"use server"

import { revalidatePath } from "next/cache"
import { z } from "zod"
import { db } from "@/lib/db"

const transactionIdSchema = z.string().regex(/^[1-9]\d{0,18}$/)
const categoryNameSchema = z.string().trim().min(1).max(120).nullable()

export async function updateTransactionCategory(transactionId: string, categoryName: string | null) {
  const id = transactionIdSchema.parse(transactionId)
  const category = categoryNameSchema.parse(categoryName)

  const updated = category === null
    ? await db`update transactions
        set category_id = null, category_source = 'manual', needs_review = false
        where id = ${id}::bigint and status = 'booked' and type <> 'ignore'
        returning id`
    : await db`update transactions as t
        set category_id = c.id, category_source = 'manual', needs_review = false
        from categories as c
        where t.id = ${id}::bigint and c.name = ${category} and c.parent_id is not null
          and t.status = 'booked' and t.type <> 'ignore'
        returning t.id`

  if (updated.length === 0) {
    throw new Error("The transaction or category could not be found.")
  }

  for (const path of ["/", "/transactions", "/monthly", "/trends", "/recurring", "/review", "/trips"]) {
    revalidatePath(path)
  }
  revalidatePath("/trips/[id]", "page")
}
