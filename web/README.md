# BMW Financial Workspace

A separate BMW-inspired edition of Finance, retaining the Frontier layouts, square components, pages, dashboards and interactions. The original and Frontier folders are preserved.

## Run

```sh
bun install
bun dev
```

Open **http://127.0.0.1:3002**. The complete app runs against synthetic sample data in its own persistent local database, `.bmw-demo/`, on port 55440. The visible Demo workspace label identifies this mode. Preview edits stay in this edition.

- Original: `/Users/troy/Desktop/finance`
- Frontier: `/Users/troy/Desktop/finance-frontier`
- BMW: `/Users/troy/Desktop/finance-bmw`

## Validation and production preview

```sh
bun run lint
bun run build
bun run preview
```

The production preview uses the same local sample database. Stop the development server before reusing the port. Override `PORT` or `BMW_DB_PORT` if needed.

## Live data

The existing ignored `.env.local` has been carried over privately. `bun run dev:live` uses that Supabase connection; edits in live mode affect the configured database. The previously unavailable live connection has not been changed by this visual edition.

See [DESIGN.md](DESIGN.md) for the visual system and asset attribution. This is an independent design concept, not an official BMW product.

---

# Finance

Finance dashboard built with Bun and Next.js, with a command-line importer for Sparkasse CSV-CAMT V2 and Revolut EUR CSV exports. The database schema is in `supabase/schema.sql`.

## Import bank exports

1. Run `bun install`.
2. Create the ignored `.env.local` with your Supabase Session pooler settings:

   ```dotenv
   SUPABASE_DB_HOST=your-session-pooler-host
   SUPABASE_DB_PORT=5432
   SUPABASE_DB_USER=postgres
   SUPABASE_DB_PASSWORD=your-database-password
   SUPABASE_DB_NAME=postgres
   ```

   Keep the real values in `.env.local`; it is excluded from Git.
3. Run `bun run import "/absolute/path/to/export.csv"`. Run the same command for each export.

Bun loads `.env.local` automatically. The script identifies the bank from the header, parses the entire file before database writes, and uses one transaction for account creation, pending-row replacement, inserts, and the import log. Repeated or overlapping exports skip existing `dedup_hash` values. It prints only row counts and the booking-date range. It does not show transaction details.

The script deletes existing pending rows for the imported account before inserting the file's rows, so each new export should include any pending rows you still want retained.

Use `bun test scripts/import.test.ts` to run the fake CSV mapping checks. Use `bun run build` to build the app.
