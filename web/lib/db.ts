import "server-only"
import postgres from "postgres"

const globalDb = globalThis as typeof globalThis & { bmwFinanceDb?: ReturnType<typeof postgres> }

export const db = globalDb.bmwFinanceDb ?? postgres(process.env.BMW_DEMO === "1" ? {
  host: "127.0.0.1",
  port: Number(process.env.BMW_DB_PORT ?? "55440"),
  username: "postgres",
  database: "postgres",
  ssl: false,
  max: 1,
} : {
  host: process.env.SUPABASE_DB_HOST,
  port: Number(process.env.SUPABASE_DB_PORT ?? "5432"),
  username: process.env.SUPABASE_DB_USER ?? "postgres",
  password: process.env.SUPABASE_DB_PASSWORD,
  database: process.env.SUPABASE_DB_NAME ?? "postgres",
  ssl: "require",
  max: 5,
})

globalDb.bmwFinanceDb = db
