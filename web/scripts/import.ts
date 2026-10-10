import { SQL } from "bun";
import { createHash } from "node:crypto";
import { basename } from "node:path";
import { parse } from "csv-parse/sync";

type CsvRow = Record<string, string>;
type Format = "sparkasse" | "revolut";
type Status = "booked" | "pending" | "reverted";
type TransactionType = "expense" | "income" | "transfer" | "cash" | "fee" | "refund" | "ignore";

type PreparedRow = {
  raw: CsvRow;
  status: Status;
  sourceType: string;
  transactedAt: string;
  bookingDate: string;
  valueDate: string | null;
  amountCents: number;
  feeCents: number;
  balanceAfterCents: number | null;
  currency: string;
  merchant: string | null;
  city: string | null;
  country: string | null;
  counterpartyRaw: string | null;
  counterpartyIban: string | null;
  descriptionRaw: string | null;
  creditorId: string | null;
  mandateRef: string | null;
  endToEndRef: string | null;
  dedupHash: string;
};

type MappedRow = PreparedRow & { type: TransactionType; needsReview: boolean };

const SPARKASSE_COLUMNS = [
  "Auftragskonto", "Buchungstag", "Valutadatum", "Buchungstext", "Verwendungszweck",
  "Glaeubiger ID", "Mandatsreferenz", "Kundenreferenz (End-to-End)",
  "Beguenstigter/Zahlungspflichtiger", "Kontonummer/IBAN", "Betrag", "Waehrung", "Info",
];
const REVOLUT_COLUMNS = [
  "Type", "Product", "Started Date", "Completed Date", "Description",
  "Amount", "Fee", "Currency", "State", "Balance",
];

class ImportError extends Error {}

function fail(message: string): never {
  throw new ImportError(message);
}

function value(row: CsvRow, key: string): string {
  return row[key] ?? "";
}

function optional(text: string): string | null {
  return text.trim() || null;
}

function hash(parts: string[]): string {
  return createHash("sha256").update(parts.join("|"), "utf8").digest("hex");
}

function normalizeIban(iban: string | null | undefined): string {
  return (iban ?? "").replace(/[\s-]/g, "").toUpperCase();
}

function dateIso(year: number, month: number, day: number): string {
  const date = new Date(Date.UTC(year, month - 1, day));
  if (date.getUTCFullYear() !== year || date.getUTCMonth() + 1 !== month || date.getUTCDate() !== day) {
    fail("Invalid date in CSV.");
  }
  return `${year.toString().padStart(4, "0")}-${month.toString().padStart(2, "0")}-${day.toString().padStart(2, "0")}`;
}

function sparkasseDate(text: string): string {
  const match = /^(\d{2})\.(\d{2})\.(\d{2})$/.exec(text.trim());
  if (!match) fail("Invalid Sparkasse date in CSV.");
  const year = Number(match[3]);
  return dateIso(year >= 80 ? 1900 + year : 2000 + year, Number(match[2]), Number(match[1]));
}

function revolutTimestamp(text: string): { timestamp: string; date: string } {
  const match = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?)?(Z|[+-]\d{2}:?\d{2})?$/.exec(text.trim());
  if (!match) fail("Invalid Revolut date in CSV.");
  const date = dateIso(Number(match[1]), Number(match[2]), Number(match[3]));
  const hour = Number(match[4] ?? "0");
  const minute = Number(match[5] ?? "0");
  const second = Number(match[6] ?? "0");
  if (hour > 23 || minute > 59 || second > 59) fail("Invalid Revolut time in CSV.");
  const clock = `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}:${String(second).padStart(2, "0")}`;
  const fraction = match[7] ? `.${match[7]}` : "";
  const zone = match[8];
  if (zone && zone !== "Z") {
    const zoneMatch = /^[+-](\d{2}):?(\d{2})$/.exec(zone);
    if (!zoneMatch || Number(zoneMatch[1]) > 23 || Number(zoneMatch[2]) > 59) fail("Invalid Revolut time zone in CSV.");
  }
  if (zone) {
    const normalizedZone = zone === "Z" ? "Z" : `${zone.slice(0, 3)}:${zone.slice(-2)}`;
    const instant = new Date(`${date}T${clock}${fraction}${normalizedZone}`);
    if (Number.isNaN(instant.getTime())) fail("Invalid Revolut timestamp in CSV.");
    return { timestamp: instant.toISOString().replace("Z", ""), date };
  }
  return { timestamp: `${date} ${clock}${fraction}`, date };
}

function cents(text: string, format: Format): number {
  const input = text.trim();
  const regex = format === "sparkasse"
    ? /^([+-]?)(\d{1,3}(?:\.\d{3})+|\d+),(\d{2})$/
    : /^([+-]?)(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?$/;
  const match = regex.exec(input);
  if (!match) fail("Invalid money amount in CSV.");
  const whole = match[2].replace(/[.,]/g, "");
  const fraction = (match[3] ?? "0").padEnd(2, "0");
  const magnitude = Number(whole) * 100 + Number(fraction);
  if (!Number.isSafeInteger(magnitude)) fail("Money amount exceeds safe integer range.");
  return match[1] === "-" ? -magnitude : magnitude;
}

function decimal(centsValue: number): string {
  if (!Number.isSafeInteger(centsValue)) fail("Money amount exceeds safe integer range.");
  const absolute = Math.abs(centsValue);
  return `${centsValue < 0 ? "-" : ""}${Math.floor(absolute / 100)}.${String(absolute % 100).padStart(2, "0")}`;
}

function header(text: string, delimiter: string): string[] {
  try {
    const records = parse(text, { delimiter, bom: true, to_line: 1, skip_empty_lines: true }) as string[][];
    return records[0] ?? [];
  } catch {
    return [];
  }
}

export function parseCsvBytes(bytes: Uint8Array): { format: Format; rows: PreparedRow[] } {
  const latin1 = new TextDecoder("iso-8859-1").decode(bytes).replace(/^ï»¿/, "");
  let format: Format;
  let text: string;
  let delimiter: string;
  const sparkasseHeader = header(latin1, ";");
  if (SPARKASSE_COLUMNS.every((column) => sparkasseHeader.includes(column))) {
    format = "sparkasse";
    text = latin1;
    delimiter = ";";
  } else {
    const utf8 = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    const revolutHeader = header(utf8, ",");
    if (!REVOLUT_COLUMNS.every((column) => revolutHeader.includes(column))) fail("Unrecognized CSV header.");
    format = "revolut";
    text = utf8;
    delimiter = ",";
  }
  const rows = parse(text, { columns: true, delimiter, bom: true, skip_empty_lines: true }) as CsvRow[];
  if (rows.length === 0) fail("CSV has no data rows.");
  return { format, rows: rows.map((row) => format === "sparkasse" ? prepareSparkasse(row) : prepareRevolut(row)) };
}

function prepareSparkasse(row: CsvRow): PreparedRow {
  const ownIban = normalizeIban(value(row, "Auftragskonto"));
  if (!ownIban) fail("Sparkasse row has no account IBAN.");
  const bookingDate = sparkasseDate(value(row, "Buchungstag"));
  const purpose = value(row, "Verwendungszweck");
  const timestamp = /^\s*(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?)/.exec(purpose)?.[1];
  const transactedAt = timestamp ? revolutTimestamp(timestamp).timestamp : bookingDate;
  const counterparty = value(row, "Beguenstigter/Zahlungspflichtiger");
  const parts = counterparty.split("/").map((part) => part.trim());
  const location = parts.length === 5 && parts[4] === "0" && /^[A-Za-z]{2}$/.test(parts[3]);
  const info = value(row, "Info").trim().toLowerCase();
  const status = info === "umsatz gebucht" ? "booked" : info === "umsatz vorgemerkt" ? "pending" : fail("Unknown Sparkasse status in CSV.");
  const currency = value(row, "Waehrung").trim().toUpperCase();
  if (!/^[A-Z]{3}$/.test(currency)) fail("Invalid currency in CSV.");
  return {
    raw: row,
    status,
    sourceType: value(row, "Buchungstext").trim(),
    transactedAt,
    bookingDate,
    valueDate: optional(value(row, "Valutadatum")) ? sparkasseDate(value(row, "Valutadatum")) : null,
    amountCents: cents(value(row, "Betrag"), "sparkasse"),
    feeCents: 0,
    balanceAfterCents: null,
    currency,
    merchant: optional(location ? parts[0] : counterparty),
    city: location ? optional(parts[2]) : null,
    country: location ? parts[3].toUpperCase() : null,
    counterpartyRaw: optional(counterparty),
    counterpartyIban: optional(value(row, "Kontonummer/IBAN")),
    descriptionRaw: optional(purpose),
    creditorId: optional(value(row, "Glaeubiger ID")),
    mandateRef: optional(value(row, "Mandatsreferenz")),
    endToEndRef: optional(value(row, "Kundenreferenz (End-to-End)")),
    dedupHash: hash(["sparkasse", ...[
      "Auftragskonto", "Buchungstag", "Betrag", "Info", "Beguenstigter/Zahlungspflichtiger",
      "Verwendungszweck", "Kundenreferenz (End-to-End)",
    ].map((key) => value(row, key))]),
  };
}

function prepareRevolut(row: CsvRow): PreparedRow {
  const started = revolutTimestamp(value(row, "Started Date"));
  const completed = optional(value(row, "Completed Date"));
  const bookingDate = completed ? revolutTimestamp(completed).date : started.date;
  const currency = value(row, "Currency").trim().toUpperCase();
  if (currency !== "EUR") fail("Revolut export contains a non-EUR row; use an EUR export for revolut_eur.");
  const state = value(row, "State").trim().toUpperCase();
  const status = state === "COMPLETED" ? "booked" : state === "PENDING" ? "pending" : state === "REVERTED" ? "reverted" : fail("Unknown Revolut state in CSV.");
  const sourceType = value(row, "Type").trim();
  const description = value(row, "Description");
  const feeCents = cents(value(row, "Fee") || "0", "revolut");
  const amountCents = cents(value(row, "Amount"), "revolut") - feeCents;
  if (!Number.isSafeInteger(amountCents)) fail("Money amount exceeds safe integer range.");
  const balance = optional(value(row, "Balance"));
  const person = /^To\s+(.+)$/i.exec(description.trim())?.[1] ?? /^Payment from\s+(.+)$/i.exec(description.trim())?.[1];
  return {
    raw: row,
    status,
    sourceType,
    transactedAt: started.timestamp,
    bookingDate,
    valueDate: null,
    amountCents,
    feeCents,
    balanceAfterCents: balance === null ? null : cents(balance, "revolut"),
    currency,
    merchant: /^Card Payment$/i.test(sourceType) ? optional(description) : null,
    city: null,
    country: null,
    counterpartyRaw: optional(person ?? description),
    counterpartyIban: null,
    descriptionRaw: optional(description),
    creditorId: null,
    mandateRef: null,
    endToEndRef: null,
    dedupHash: hash(["revolut", "revolut_eur", ...[
      "Type", "Started Date", "Amount", "Fee", "Currency", "Description",
    ].map((key) => value(row, key))]),
  };
}

function nameKey(name: string): string {
  return name.toLocaleLowerCase().match(/[\p{L}\p{N}]+/gu)?.sort().join(" ") ?? "";
}

function isOwn(counterparty: string | null, iban: string | null, ownerNames: string[], ownIbans: Set<string>): boolean {
  const normalizedIban = normalizeIban(iban);
  if (normalizedIban && ownIbans.has(normalizedIban)) return true;
  const key = nameKey(counterparty ?? "");
  return Boolean(key) && ownerNames.some((name) => nameKey(name) === key);
}

export function classify(row: PreparedRow, format: Format, ownerNames: string[], ownIbans: Set<string>, ownCards: Set<string>): MappedRow {
  const source = row.sourceType.toUpperCase();
  const description = row.descriptionRaw ?? "";
  const own = isOwn(row.counterpartyRaw, row.counterpartyIban, ownerNames, ownIbans);
  let type: TransactionType;
  let needsReview = false;
  if (format === "sparkasse") {
    if (source === "ABSCHLUSS") type = "ignore";
    else if (source === "RECHNUNG") type = "fee";
    else if (source === "WIEDERGUTSCHRIFT") type = "refund";
    else if (/^LOHN\s+GEHALT$/.test(source)) type = "income";
    else if (/^BARGELDAUSZAHLUNG|GELDAUTOMAT|^AUSZAHL\. MIT KUNDENENTGELT/.test(source)) type = "cash";
    else if (source === "KARTENZAHLUNG") type = row.amountCents >= 0 ? "refund" : "expense";
    else if (source === "E-COM (APPLE PAY)") type = /REVOLUT/i.test(`${description} ${row.counterpartyRaw ?? ""}`) ? "transfer" : "expense";
    else if (source === "DIG. KARTE (APPLE PAY)" || source.includes("LASTSCHRIFT")) type = "expense";
    else if (source.endsWith("UEBERWEISUNG") || source.endsWith("ÜBERWEISUNG")) type = own ? "transfer" : "expense";
    else if (source.endsWith("GUTSCHRIFT") || source.startsWith("GUTSCHR.")) type = own ? "transfer" : "income";
    else { type = row.amountCents >= 0 ? "income" : "expense"; needsReview = true; }
  } else {
    if (source === "CARD PAYMENT") type = "expense";
    else if (source === "CARD REFUND") type = "refund";
    else if (source === "REWARD") type = "income";
    else if (source === "EXCHANGE") type = "transfer";
    else if (source === "TOPUP") {
      const appleCard = /APPLE PAY TOP-UP BY\s+\*(\d{4})/i.exec(description)?.[1];
      if (appleCard) type = ownCards.has(appleCard) ? "transfer" : "income";
      else if (/^PAYMENT FROM\s+/i.test(description)) type = own ? "transfer" : "income";
      else { type = row.amountCents >= 0 ? "income" : "expense"; needsReview = true; }
    } else if (source === "TRANSFER") {
      if (/^TO\s+/i.test(description)) type = own ? "transfer" : "expense";
      else { type = row.amountCents >= 0 ? "income" : "expense"; needsReview = true; }
    } else { type = row.amountCents >= 0 ? "income" : "expense"; needsReview = true; }
  }
  return { ...row, type, needsReview };
}

export async function importFile(path: string): Promise<{ rowsInFile: number; inserted: number; skipped: number; dateFrom: string; dateTo: string }> {
  const bytes = new Uint8Array(await Bun.file(path).arrayBuffer());
  const { format, rows } = parseCsvBytes(bytes);
  const projectHost = process.env.SUPABASE_DB_HOST?.trim();
  const password = process.env.SUPABASE_DB_PASSWORD;
  if (!projectHost || !password) fail("Set SUPABASE_DB_HOST and SUPABASE_DB_PASSWORD in .env.local before importing.");
  const ownerNames = (process.env.OWNER_NAMES ?? "").split(",").map((name) => name.trim()).filter(Boolean);
  const ownCards = new Set((process.env.OWN_CARD_LAST4 ?? "").split(",").map((card) => card.trim()).filter(Boolean));
  const dateFrom = rows.map((row) => row.bookingDate).sort()[0];
  const dateTo = rows.map((row) => row.bookingDate).sort().at(-1)!;
  const fileHash = createHash("sha256").update(bytes).digest("hex");
  const sql = new SQL({
    hostname: projectHost,
    port: Number(process.env.SUPABASE_DB_PORT ?? "5432"),
    username: process.env.SUPABASE_DB_USER ?? "postgres",
    password,
    database: process.env.SUPABASE_DB_NAME ?? "postgres",
    tls: true,
    max: 1,
  });
  try {
    return await sql.begin(async (tx) => {
      const accountIban = format === "sparkasse" ? normalizeIban(value(rows[0].raw, "Auftragskonto")) : "";
      if (format === "sparkasse" && rows.some((row) => normalizeIban(value(row.raw, "Auftragskonto")) !== accountIban)) {
        fail("Sparkasse CSV contains more than one account IBAN.");
      }
      let accounts = await tx`select id, iban from accounts` as Array<{ id: string; iban: string | null }>;
      let accountId: string;
      if (format === "sparkasse") {
        const matched = accounts.find((account) => normalizeIban(account.iban) === accountIban);
        if (matched) accountId = matched.id;
        else {
          const existingId = accounts.find((account) => account.id === "sparkasse_giro");
          if (existingId && normalizeIban(existingId.iban)) fail("sparkasse_giro already belongs to a different IBAN.");
          if (existingId) {
            await tx`update accounts set iban = ${accountIban} where id = 'sparkasse_giro'`;
          } else {
            await tx`insert into accounts (id, name, institution, iban, currency, source_format)
              values ('sparkasse_giro', 'Sparkasse Giro', 'Sparkasse', ${accountIban}, 'EUR', 'sparkasse_csv_camt_v2')`;
          }
          accountId = "sparkasse_giro";
        }
      } else {
        await tx`insert into accounts (id, name, institution, currency, source_format)
          values ('revolut_eur', 'Revolut EUR', 'Revolut', 'EUR', 'revolut_csv')
          on conflict (id) do nothing`;
        accountId = "revolut_eur";
      }
      accounts = await tx`select id, iban from accounts` as Array<{ id: string; iban: string | null }>;
      const ownIbans = new Set(accounts.map((account) => normalizeIban(account.iban)).filter(Boolean));
      const mapped = rows.map((row) => classify(row, format, ownerNames, ownIbans, ownCards));
      const deleted = await tx`delete from transactions where account_id = ${accountId} and status = 'pending' returning 1`;
      const [importRecord] = await tx`insert into imports
        (account_id, file_name, file_sha256, rows_in_file, rows_inserted, rows_skipped, pending_replaced, date_from, date_to)
        values (${accountId}, ${basename(path)}, ${fileHash}, ${rows.length}, 0, 0, ${deleted.length}, ${dateFrom}::date, ${dateTo}::date)
        returning id`;
      let inserted = 0;
      for (const row of mapped) {
        const saved = await tx`insert into transactions (
          account_id, import_id, status, type, transacted_at, booking_date, value_date,
          amount, fee, currency, balance_after, source_type, merchant, city, country,
          counterparty_raw, counterparty_iban, description_raw, creditor_id, mandate_ref,
          end_to_end_ref, needs_review, dedup_hash, raw
        ) values (
          ${accountId}, ${importRecord.id}, ${row.status}::txn_status, ${row.type}::txn_type,
          ${row.transactedAt}::timestamp, ${row.bookingDate}::date, ${row.valueDate}::date,
          ${decimal(row.amountCents)}::numeric, ${decimal(row.feeCents)}::numeric,
          ${row.currency}, ${row.balanceAfterCents === null ? null : decimal(row.balanceAfterCents)}::numeric,
          ${row.sourceType}, ${row.merchant}, ${row.city}, ${row.country},
          ${row.counterpartyRaw}, ${row.counterpartyIban}, ${row.descriptionRaw},
          ${row.creditorId}, ${row.mandateRef}, ${row.endToEndRef}, ${row.needsReview},
          ${row.dedupHash}, ${JSON.stringify(row.raw)}::jsonb
        ) on conflict (dedup_hash) do nothing returning 1`;
        inserted += saved.length;
      }
      await tx`update transactions as t
        set merchant = coalesce(rule.set_merchant, t.merchant),
            type = coalesce(rule.set_type, t.type),
            category_id = coalesce(rule.set_category_id, t.category_id),
            category_source = case
              when rule.set_category_id is not null then 'rule'::category_source
              else t.category_source
            end
        from lateral (
          select mr.set_merchant, mr.set_type, mr.set_category_id
          from merchant_rules as mr
          where (mr.account_id is null or mr.account_id = t.account_id)
            and case mr.match_field
              when 'merchant' then t.merchant
              when 'counterparty_raw' then t.counterparty_raw
              when 'description_raw' then t.description_raw
              when 'source_type' then t.source_type
            end ~* mr.pattern
          order by mr.priority asc, mr.id asc
          limit 1
        ) as rule
        where t.import_id = ${importRecord.id}
          and (t.category_source is null or t.category_source = 'rule')`;
      await tx`update transactions
        set category_id = case
              when type = 'transfer' then (select id from categories where name = 'Internal Transfer')
              when type = 'cash' then (select id from categories where name = 'Cash Withdrawals')
              when type = 'fee' then (select id from categories where name = 'Bank Fees')
              when source_type = 'LOHN  GEHALT' then (select id from categories where name = 'Salary')
              when source_type = 'Reward' then (select id from categories where name = 'Cashback & Rewards')
            end,
            category_source = 'rule'
        where import_id = ${importRecord.id}
          and category_id is null
          and (category_source is null or category_source = 'rule')
          and (type in ('transfer', 'cash', 'fee')
            or source_type in ('LOHN  GEHALT', 'Reward'))`;
      const skipped = rows.length - inserted;
      await tx`update imports set rows_inserted = ${inserted}, rows_skipped = ${skipped} where id = ${importRecord.id}`;
      return { rowsInFile: rows.length, inserted, skipped, dateFrom, dateTo };
    });
  } finally {
    await sql.close();
  }
}

if (import.meta.main) {
  const path = process.argv[2];
  if (!path || process.argv.length !== 3) {
    console.error("Usage: bun run import <path-to-csv>");
    process.exitCode = 1;
  } else {
    try {
      const result = await importFile(path);
      console.log(`Rows in file: ${result.rowsInFile}`);
      console.log(`Inserted: ${result.inserted}`);
      console.log(`Skipped as duplicates: ${result.skipped}`);
      console.log(`Date range: ${result.dateFrom} to ${result.dateTo}`);
    } catch (error) {
      if (error instanceof ImportError) {
        console.error(error.message);
      } else if (error instanceof Error && /password authentication failed/i.test(error.message)) {
        console.error("Database password was rejected. Check SUPABASE_DB_PASSWORD in .env.local; no changes were committed.");
      } else {
        console.error("Import failed; no changes were committed.");
      }
      process.exitCode = 1;
    }
  }
}
