import { PGlite } from '@electric-sql/pglite'
import { PGLiteSocketServer } from '@electric-sql/pglite-socket'
import { readFile } from 'node:fs/promises'
import { spawn } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const port = Number(process.env.BMW_DB_PORT || 55440)
const db = await PGlite.create(path.join(root, '.bmw-demo'))
const existing = await db.query("select to_regclass('public.transactions') as table_name")
if (!existing.rows[0].table_name) {
  await db.exec('create role anon; create role authenticated; create role service_role;')
  await db.exec(await readFile(path.join(root, 'supabase/schema.sql'), 'utf8'))
  await seed(db)
  console.log('Created an isolated demo database with sample accounts, transactions and trips.')
}
const server = new PGLiteSocketServer({ db, host: '127.0.0.1', port, maxConnections: 5 })
await server.start()
console.log(`BMW demo database ready on 127.0.0.1:${port}. No live bank connection is used.`)
const mode = process.argv.includes('--production') ? 'start' : 'dev'
const child = spawn(process.execPath, ['node_modules/next/dist/bin/next', mode, '--hostname', '127.0.0.1', '--port', process.env.PORT || '3002'], {
  cwd: root, stdio: 'inherit',
  env: { ...process.env, BMW_DEMO: '1', BMW_DB_PORT: String(port) },
})
let closing = false
async function close(code = 0) {
  if (closing) return
  closing = true
  child.kill('SIGTERM')
  await server.stop()
  await db.close()
  process.exit(code)
}
process.on('SIGINT', () => close())
process.on('SIGTERM', () => close())
child.on('exit', code => close(code || 0))
child.on('error', error => { console.error(error.message); close(1) })

async function seed(database) {
  const date = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Madrid', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
  const end = new Date(`${date}T12:00:00Z`)
  const start = new Date(Date.UTC(end.getUTCFullYear(), end.getUTCMonth() - 13, 1, 12))
  const categories = new Map((await database.query('select id, name from categories')).rows.map(row => [row.name, row.id]))
  let randomSeed = 72419
  const random = () => { randomSeed = (randomSeed * 1664525 + 1013904223) >>> 0; return randomSeed / 4294967296 }
  const merchants = [
    ['Edeka', 'Groceries', 28, 61], ['REWE', 'Groceries', 19, 46],
    ['Mercadona', 'Groceries', 16, 53], ['Café Federal', 'Cafe / Bakery', 5, 14],
    ['Honest Greens', 'Restaurants', 13, 26], ['La Maruca', 'Restaurants', 29, 64],
    ['Deutsche Bahn', 'Public Transport', 9, 34], ['Metro de Madrid', 'Public Transport', 3, 11],
    ['Uber', 'Taxi & Rideshare', 12, 30], ['COS', 'Shopping', 39, 128],
    ['MUJI', 'Shopping', 12, 39], ['Bunq ATM', 'Cash & Fees', 40, 100],
    ['Gorillas', 'Delivery', 18, 37], ['Pret A Manger', 'Fast Food', 7, 14],
    ['Cinema Ideal', 'Going Out', 12, 27], ['Farmacia Central', 'Other Health', 8, 34],
  ]
  await database.transaction(async tx => {
    await tx.exec("insert into accounts (id,name,institution,currency) values ('sparkasse_giro','Sparkasse','Sparkasse','EUR'), ('revolut_eur','Revolut','Revolut','EUR')")
    let index = 0
    async function insert(day, merchant, category, amount, account, type = 'expense') {
      index++
      await tx.query(`insert into transactions (account_id,status,type,booking_date,transacted_at,amount,currency,source_type,merchant,description_raw,category_id,category_source,needs_review,dedup_hash,raw)
        values ($1,'booked',$2,$3::date,$3::date + interval '12 hours',$4,'EUR','Demo entry',$5,$6,$7,'rule',$8,$9,'{}')`,
        [account, type, day, amount, merchant, `Sample transaction: ${merchant}`, category ? categories.get(category) : null, category == null, `bmw-demo-${index}`,])
    }
    for (const d = new Date(start); d <= end; d.setUTCDate(d.getUTCDate() + 1)) {
      const day = d.toISOString().slice(0, 10)
      const dayOfMonth = d.getUTCDate()
      if (dayOfMonth === 1) {
        await insert(day, 'Monthly salary', 'Salary', 4250, 'sparkasse_giro', 'income')
        await insert(day, 'Eukia Vermietungs- und Verwaltungs GmbH', 'Rent', -1090, 'sparkasse_giro')
        await insert(day, 'PYUR', 'Internet & Phone', -24.99, 'sparkasse_giro')
      }
      if (dayOfMonth === 12) {
        await insert(day, 'Spotify', 'Other Subscriptions', -6.99, 'revolut_eur')
        await insert(day, 'ANTHROPIC', 'AI Tools', -21.42, 'revolut_eur')
      }
      if (dayOfMonth === 20 && random() > 0.4) await insert(day, 'Advisory project', 'Freelance', 675 + Math.round(random() * 850), 'sparkasse_giro', 'income')
      const count = 1 + Math.floor(random() * 4)
      for (let i = 0; i < count; i++) {
        const [merchant, category, min, max] = merchants[Math.floor(random() * merchants.length)]
        const amount = Math.round((min + random() * (max - min)) * 100) / 100
        await insert(day, merchant, random() < 0.035 ? null : category, -amount, random() > 0.38 ? 'revolut_eur' : 'sparkasse_giro', merchant === 'Bunq ATM' ? 'cash' : 'expense')
      }
    }
    for (const [name, destination, months, from, to, notes] of [
      ['Madrid', 'Madrid, Spain', 1, 5, 12, 'A week in the city.'],
      ['Copenhagen', 'Copenhagen, Denmark', 2, 15, 19, 'Summer travel and a long weekend.'],
      ['Lisbon', 'Lisbon, Portugal', 4, 8, 14, 'Travel, dining and accommodation.'],
    ]) {
      const startDate = new Date(Date.UTC(end.getUTCFullYear(), end.getUTCMonth() - months, from, 12)).toISOString().slice(0, 10)
      const endDate = new Date(Date.UTC(end.getUTCFullYear(), end.getUTCMonth() - months, to, 12)).toISOString().slice(0, 10)
      await tx.query('insert into trips (name,destination,start_date,end_date,notes) values ($1,$2,$3,$4,$5)', [name,destination,startDate,endDate,notes])
    }
    for (const account of ['sparkasse_giro','revolut_eur']) await tx.query("insert into imports (account_id,file_name,file_sha256,rows_in_file,rows_inserted,rows_skipped,date_from,date_to) values ($1,'Sample data','demo',500,500,0,$2,$3)", [account,start.toISOString().slice(0,10),date])
  })
}
