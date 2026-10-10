"use server"

import { revalidatePath } from "next/cache"
import { z } from "zod"
import { db } from "@/lib/db"

const date = z.iso.date().refine((value) => value >= "1900-01-01" && value <= "2100-12-31", "Date is out of range")
const tripInput = z.object({
  name: z.string().trim().min(1).max(120),
  destination: z.string().trim().max(120).optional().nullable(),
  start_date: date,
  end_date: date,
  notes: z.string().trim().max(5000).optional().nullable(),
}).refine((value) => value.end_date >= value.start_date, {
  path: ["end_date"], message: "End date must be on or after start date",
})
const idSchema = z.string().regex(/^[1-9]\d{0,18}$/)
export type TripInput = z.input<typeof tripInput>

function refreshTrip(id?: string) {
  revalidatePath("/trips")
  if (id) revalidatePath(`/trips/${id}`)
}

export async function createTrip(input: TripInput) {
  const trip = tripInput.parse(input)
  const rows = await db`insert into trips (name, destination, start_date, end_date, notes)
    values (${trip.name}, ${trip.destination || null}, ${trip.start_date}::date, ${trip.end_date}::date, ${trip.notes || null})
    returning id::text as id`
  refreshTrip()
  return String(rows[0].id)
}

export async function updateTrip(id: string, input: TripInput) {
  const tripId = idSchema.parse(id)
  const trip = tripInput.parse(input)
  await db`update trips set name = ${trip.name}, destination = ${trip.destination || null},
    start_date = ${trip.start_date}::date, end_date = ${trip.end_date}::date, notes = ${trip.notes || null}
    where id = ${tripId}::bigint`
  refreshTrip(tripId)
}

export async function deleteTrip(id: string) {
  const tripId = idSchema.parse(id)
  await db`delete from trips where id = ${tripId}::bigint`
  refreshTrip(tripId)
}

async function setOverride(tripId: string, transactionId: string, included: boolean) {
  const trip = idSchema.parse(tripId)
  const transaction = idSchema.parse(transactionId)
  await db`insert into trip_transactions (trip_id, transaction_id, included)
    select ${trip}::bigint, t.id, ${included}
    from v_transactions t where t.id = ${transaction}::bigint
      and t.type in ('expense', 'cash', 'fee', 'refund')
      and t.parent_category is distinct from 'Housing & Utilities'
    on conflict (trip_id, transaction_id) do update set included = excluded.included`
  refreshTrip(trip)
}

export async function excludeTransaction(tripId: string, transactionId: string) {
  await setOverride(tripId, transactionId, false)
}

export async function includeTransaction(tripId: string, transactionId: string) {
  await setOverride(tripId, transactionId, true)
}

export async function resetTransaction(tripId: string, transactionId: string) {
  const trip = idSchema.parse(tripId)
  const transaction = idSchema.parse(transactionId)
  await db`delete from trip_transactions where trip_id = ${trip}::bigint and transaction_id = ${transaction}::bigint`
  refreshTrip(trip)
}
