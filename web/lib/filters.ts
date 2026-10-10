export type Params = Record<string, string | string[] | undefined>
export type Range = { from: string | null; to: string | null }
export type Filters = Range & { account: string | null }
export const ALL_TIME_URL = { from: "0001-01-01", to: "9999-12-31" } as const

export function globalFilterQuery(params: Params): string {
  const query = new URLSearchParams()
  for (const key of ["account", "from", "to", "range"]) {
    const value = param(params, key)
    if (value) query.set(key, value)
  }
  return query.toString()
}

export function param(params: Params, key: string): string | undefined {
  const value = params[key]
  return typeof value === "string" ? value : undefined
}

export function today(): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Europe/Madrid", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(new Date())
  const part = (type: string) => parts.find((item) => item.type === type)?.value ?? ""
  return `${part("year")}-${part("month")}-${part("day")}`
}

export function shiftDate(iso: string, days: number): string {
  const date = new Date(`${iso}T12:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

export function monthStart(iso: string, offset = 0): string {
  const date = new Date(`${iso.slice(0, 7)}-01T12:00:00Z`)
  date.setUTCMonth(date.getUTCMonth() + offset)
  return date.toISOString().slice(0, 10)
}

export function presetRange(preset: string, now = today()): Range {
  const thisMonth = monthStart(now)
  if (preset === "all") return { from: null, to: null }
  if (preset === "this") return { from: thisMonth, to: now }
  if (preset === "last") return { from: monthStart(now, -1), to: shiftDate(thisMonth, -1) }
  const count = preset === "3m" ? 3 : preset === "12m" ? 12 : 6
  return { from: monthStart(now, 1 - count), to: now }
}

function validDate(value: string | undefined): value is string {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const date = new Date(`${value}T12:00:00Z`)
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value
}

export function resolveFilters(params: Params, defaultPreset = "6m"): Filters {
  const account = param(params, "account")
  const from = param(params, "from")
  const to = param(params, "to")
  const range = param(params, "range") === "all" || (from === ALL_TIME_URL.from && to === ALL_TIME_URL.to)
    ? { from: null, to: null }
    : validDate(from) && validDate(to) && from <= to && from >= "1900-01-01" && to <= "2100-12-31"
      ? { from, to }
      : presetRange(defaultPreset)
  return { ...range, account: account === "sparkasse_giro" || account === "revolut_eur" ? account : null }
}

export function previousRange(range: Range): Range | null {
  if (!range.from || !range.to) return null
  const days = Math.round((Date.parse(range.to) - Date.parse(range.from)) / 86400000) + 1
  return { from: shiftDate(range.from, -days), to: shiftDate(range.from, -1) }
}

export function selectedMonth(params: Params): string {
  const value = param(params, "month")
  return value && /^(19|20)\d{2}-(0[1-9]|1[0-2])$/.test(value) ? value : monthStart(today(), -1).slice(0, 7)
}

export function formatDate(value: string | null | undefined): string {
  return value ? `${value.slice(8, 10)}.${value.slice(5, 7)}.${value.slice(0, 4)}` : "—"
}

export const money = new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" })
